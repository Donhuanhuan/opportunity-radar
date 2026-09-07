"""内容工厂 · 双版本文案生成（小红书 + 知乎）

输入：item（商机原始 dict）+ analyze_result（来自 analyze.py）
输出：{
  "xhs": {
    "title": "...",
    "body": "...",
    "hashtags": ["..."],
    "image_prompts": ["..."],
    "publish_tip": "..."
  },
  "zh": {
    "titles": ["...", "...", "..."],  # 3 种风格标题备选
    "body": "...",
    "key_points": ["..."],
    "image_prompts": ["..."],
    "publish_tip": "..."
  },
  "llm_used": "..."
}

无 LLM key 时降级为「模板式生成」。
"""
import json
import os
import re
import urllib.request
import urllib.error
from typing import Any

# 复用 analyze.py 的 provider 抽象
from content_factory.analyze import (
    _call_openai, _call_deepseek, _call_claude,
    _extract_json, LLM_TIMEOUT, _norm_item,
)

# ============ 小红书 ============

_XHS_SYSTEM = """你是小红书爆款种草文案专家。任务：给定一条英文/中文商机，把它改成「小红书爆款笔记」。

风格要求：
1. 标题：用 emoji + 数字 + 痛点关键词（≤ 22 字）
2. 开头：第 1 句话必须有钩子（疑问/数据/反差/痛点画面）
3. 中段：短段落 + 多 emoji + 互动词（姐妹们/宝子们/亲测）
4. 末尾：必须有 CTA（收藏 / 评论区蹲）
5. 正文 ≤ 500 字
6. hascodes 中文标签 3-6 个
7. image_prompts 输出 3 张图的中文描述（用于 Midjourney / 即梦 / LibTV）
8. publish_tip 给作者本人看的"发布要点"（封面建议 / 最佳时间段 / 评论引导）

⚠️ 不要生硬翻译，必须本土化（中国人说话的方式）。
⚠️ 严禁任何违规词（绝对化用语 / 医疗 / 投资承诺）。
只输出 JSON。"""

_XHS_USER_TEMPLATE = """【商机】
title: {title}
source: {source}
score: {score}
summary: {summary}

【分析结果】
angle: {angle}
audience: {audience}
pain_point: {pain_point}
value_prop: {value_prop}
xhs_angle: {xhs_angle}
image_prompts_seed: {image_prompts_seed}
key_facts: {key_facts}

【输出 JSON】
{{
  "title": "...",
  "body": "...",
  "hashtags": ["..."],
  "image_prompts": ["..."],
  "publish_tip": "..."
}}"""


def _gen_xhs(item: dict, analysis: dict) -> dict:
    user_prompt = _XHS_USER_TEMPLATE.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        score=item.get("score", 0),
        summary=item.get("summary", ""),
        angle=analysis.get("angle", ""),
        audience=analysis.get("audience", ""),
        pain_point=analysis.get("pain_point", ""),
        value_prop=analysis.get("value_prop", ""),
        xhs_angle=analysis.get("xhs_angle", ""),
        image_prompts_seed="|".join(analysis.get("image_prompts") or []) or "无",
        key_facts="|".join(analysis.get("key_facts") or []) or "无",
    )
    raw = _call_selected_llm(_XHS_SYSTEM, user_prompt)
    return _extract_json(raw)


# ============ 知乎 ============

_ZH_SYSTEM = """你是知乎大 V，专做深度技术 / 工具 / 商业分析。任务：给定一条商机，改写成「知乎优秀回答」风格的长文。

风格要求：
1. 给出 3 种标题（理性 / 悬念 / 实用），每个 ≤ 30 字
2. 正文结构：
   - 引入（用问题或现象作开头，2-3 句）
   - 主体 3-5 个核心观点（每个观点 1-2 段）
   - 实操 / 对比 / 资源建议
   - 个人判断 / 行业洞察（至少 1 段）
   - 结尾留钩（提问 / 邀请讨论）
3. 篇幅 800-1500 字
4. 段落用清晰层次（可用 1./2./3. 序号）
5. 严禁违规词 / 软广口吻不能太明显
6. key_points 列出 3-5 个核心论点
7. image_prompts 输出封面 / 配图的中文描述
8. publish_tip 给出"发布要点"（知乎问题选择 / 首发时间 / 评论引导）

只输出 JSON。"""

_ZH_USER_TEMPLATE = """【商机】
title: {title}
source: {source}
score: {score}
summary: {summary}

【分析】
angle: {angle}
audience: {audience}
pain_point: {pain_point}
value_prop: {value_prop}
zh_angle: {zh_angle}
image_prompts_seed: {image_prompts_seed}
key_facts: {key_facts}

【输出 JSON】
{{
  "titles": ["理性派标题", "悬念标题", "实用标题"],
  "body": "...",
  "key_points": ["..."],
  "image_prompts": ["..."],
  "publish_tip": "..."
}}"""


def _gen_zh(item: dict, analysis: dict) -> dict:
    user_prompt = _ZH_USER_TEMPLATE.format(
        title=item.get("title", ""),
        source=item.get("source", ""),
        score=item.get("score", 0),
        summary=item.get("summary", ""),
        angle=analysis.get("angle", ""),
        audience=analysis.get("audience", ""),
        pain_point=analysis.get("pain_point", ""),
        value_prop=analysis.get("value_prop", ""),
        zh_angle=analysis.get("zh_angle", ""),
        image_prompts_seed="|".join(analysis.get("image_prompts") or []) or "无",
        key_facts="|".join(analysis.get("key_facts") or []) or "无",
    )
    raw = _call_selected_llm(_ZH_SYSTEM, user_prompt)
    return _extract_json(raw)


# ============ LLM Provider 选择 ============

def _call_selected_llm(system: str, user: str) -> str:
    """自动选 provider（与 analyze.py 同款，但内部封装）"""
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return _call_openai(api_key, system, user)
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        return _call_deepseek(api_key, system, user)
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
    if api_key:
        return _call_claude(api_key, system, user)
    raise RuntimeError("NO_LLM_KEY")


# ============ 模板兜底（无 key 时）============

def _template_xhs(item: dict, analysis: dict) -> dict:
    title = item.get("title", "这条")
    summary = item.get("summary", "")[:120]
    return {
        "title": f"🔥 {title[:18]}·亲测避坑",
        "body": (
            f"姐妹们，这条必须曝光 ✨\n\n"
            f"{summary}\n\n"
            f"亮点：{analysis.get('value_prop', '够快够好用')}\n\n"
            f"👀 适合人群：{analysis.get('audience', '全体打工人')}\n\n"
            f"💡 小技巧：先收藏，第 3 天再回看，效果翻倍\n\n"
            f"评论区蹲蹲，看你们的体验 🙋‍♀️"
        ),
        "hashtags": analysis.get("hashtags") or ["AI工具", "效率", "干货分享"],
        "image_prompts": [
            f"封面：{title[:30]}，霓虹渐变 + 大字突出痛点",
            "对比图：'用之前' vs '用之后' 的左右分屏",
            "细节图：操作界面 + 关键功能高亮",
        ],
        "publish_tip": "📌 封面用第 1 张图；建议 12:00-14:00 或 19:00-22:00 发；评论区自己置顶一条问句引讨论",
        "llm_used": "template",
    }


def _template_zh(item: dict, analysis: dict) -> dict:
    title = item.get("title", "这条")
    summary = item.get("summary", "")
    points = analysis.get("key_facts") or [analysis.get("value_prop", "实用性高")]
    body_parts = [
        f"## 为什么我在关注 {title}",
        f"{summary}",
        f"我作为{analysis.get('audience', '一线用户')}，看完之后想从 3 个角度分享一下：\n",
    ]
    for i, p in enumerate(points[:5], 1):
        body_parts.append(f"### {i}. {p}\n")
    body_parts.extend([
        f"## 我的结论",
        f"如果你是{analysis.get('audience', '有相关需求的人')}，{analysis.get('value_prop', '值得一试')}。",
        f"你怎么看？你目前用的是什么工具？欢迎评论区交流。",
    ])
    body = "\n\n".join(body_parts)
    return {
        "titles": [
            f"{title}，你怎么看？",
            f"聊聊 {title} 的真实使用感受",
            f"{title} 值不值得用？深度拆解",
        ],
        "body": body,
        "key_points": points[:5],
        "image_prompts": [
            f"封面：{title[:30]}，极简几何，蓝色主调",
            "对比图：左传统右新方案，简化版 vs 完整版",
            "数据/截图图：核心功能展示",
        ],
        "publish_tip": "📌 绑定热门问题（搜索「{title[:8]}」）；建议 9:00 或 21:00 发；前 30 分钟自己评论置顶 1 个延展问题引导讨论",
        "llm_used": "template",
    }


# ============ 主入口 ============

def generate(item: dict, analysis: dict | None = None) -> dict:
    """生成小红书 + 知乎双版本文案

    analysis: 可选。如果没传，会自动调用 analyze.analyze()
    """
    if analysis is None:
        from content_factory.analyze import analyze as do_analyze
        analysis = do_analyze(item)

    it = _norm_item(item)
    out = {"title": it["title"], "source": it["source"], "score": it["score"]}
    try:
        xhs = _gen_xhs(it, analysis)
        out["xhs"] = {**xhs, "llm_used": xhs.get("llm_used", _get_provider_name())}
    except Exception as e:
        out["xhs"] = {**_template_xhs(it, analysis), "error": str(e)[:120]}
        out["xhs"]["llm_used"] = "template"

    try:
        zh = _gen_zh(it, analysis)
        out["zh"] = {**zh, "llm_used": zh.get("llm_used", _get_provider_name())}
    except Exception as e:
        out["zh"] = {**_template_zh(it, analysis), "error": str(e)[:120]}
        out["zh"]["llm_used"] = "template"

    out["analysis"] = analysis
    return out


def _get_provider_name() -> str:
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("DEEPSEEK_API_KEY"):
        return "deepseek"
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"):
        return "claude"
    return "rules"


# ============ Demo ============

if __name__ == "__main__":
    import sys
    sample = {
        "title": "Cursor launches Agent Mode for autonomous coding",
        "url": "https://cursor.com",
        "source": "hackernews",
        "score": 88,
        "summary": "AI code editor Cursor now supports autonomous agent that can read/write whole project.",
        "tags": ["hot", "demand"],
    }
    from content_factory.analyze import analyze
    a = analyze(sample)
    result = generate(sample, a)
    print(json.dumps(result, ensure_ascii=False, indent=2))
