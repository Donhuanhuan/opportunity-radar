# -*- coding: utf-8 -*-
"""质检闸单元测试（不调 LLM，不写飞书）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from agents.orchestrator import _hard_quality_check, _qc_summary, load_agent

ok = True

def check(name, got, expect):
    global ok
    passed = got == expect
    ok = ok and passed
    print(f"{'✅' if passed else '❌'} {name}: got={got} expect={expect}")

# 1. 合格的小红书内容 → 无问题
title = "被裁员那天，我反而松了口气"
body = "那天下午HR约我谈话，我心里就有数了。\n\n走出公司大门，阳光好刺眼，我居然笑了。\n\n失业三个月，我把日子过成了想要的节奏：早睡早起，自己做饭，把收藏夹里落灰的教程一个个看完。\n\n原来停下来，不是躺平，是换个姿势出发。姐妹们，你们有没有过这种'坏事变好事'的瞬间？评论区聊聊👇"
check("合格小红书", _hard_quality_check("小红书", title, body), [])

# 2. AI 腔 → 命中
check("AI腔用词", "AI 腔用词: 「首先」" in str(_hard_quality_check("小红书", "测试标题内容", "首先，我想说这个话题。\n\n其次，我们要看到。")), True)

# 3. 标题超长（小红书 > 25）
check("标题超长", any("标题超长" in i for i in _hard_quality_check("小红书", "这是一个特别特别特别特别特别特别特别长的标题超过二十五个字了", "正文" * 100)), True)

# 4. 正文过短（知乎 < 300）
short_body = "很短的正文。"
check("知乎正文过短", any("正文过短" in i for i in _hard_quality_check("知乎", "正常长度标题", short_body)), True)

# 5. 模板变量残留
check("模板残留", any("模板" in i for i in _hard_quality_check("小红书", "测试标题", "正文里有 {title} 变量没替换，还有 ```json fence")), True)

# 6. 标题与正文首行重复
check("标题重复首行", any("重复" in i for i in _hard_quality_check("知乎", "完全相同的标题文字", "完全相同的标题文字\n\n后面是正文内容" * 30)), True)

# 7. 知乎合格长文 → 无问题
zh_body = "开头场景。\n\n## 第一部分\n\n" + ("知乎风格的长正文内容，讲道理有层次有细节，符合八百字以上的要求。" * 30)
check("合格知乎", _hard_quality_check("知乎", "35岁被优化的人后来都怎么样了", zh_body), [])

# 8. _qc_summary 格式
check("摘要-通过", _qc_summary({"passed": True, "score": 86, "rule_issues": [], "llm": {}}), "QC: 86")
check("摘要-拦截", "未达标" in _qc_summary({"passed": False, "score": 58, "rule_issues": ["标题超长(30字 > 25)"], "llm": {}}), True)
check("摘要-rules", _qc_summary({"passed": True, "score": -1, "rule_issues": [], "llm": {}}), "QC: rules")

# 9. quality_reviewer.yaml 可加载且 prompt 模板占位符正确
agent = load_agent("quality_reviewer")
tpl = agent["llm_prompt_template"]
check("yaml模板占位符", all(k in tpl for k in ("{platform}", "{title}", "{body}", "{min_score}")), True)

print("\n" + ("🎉 全部通过" if ok else "💥 有失败项"))
sys.exit(0 if ok else 1)
