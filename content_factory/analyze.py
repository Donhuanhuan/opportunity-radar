"""内容工厂 · LLM 分析商机

输入：radar.scan() 抓到的一条商机 dict
输出：{
  angle, audience, pain_point, value_prop,
  xhs_angle, zh_angle, hashtags, image_prompts[],
  llm_used (openai/claude/deepseek/rules)
}

支持多 LLM provider（自动从环境变量选 key）：
- OPENAI_API_KEY  → OpenAI gpt-4o-mini
- ANTHROPIC_API_KEY → Claude claude-sonnet-4
- DEEPSEEK_API_KEY  → DeepSeek-V3（国产，便宜）

无 key 时降级为「规则提取」，保证流程不挂。
"""
import json
import os
import re
import urllib.request
import urllib.error
from typing import Any

LLM_TIMEOUT = 30
_USER_TITLE_PATTERNS = [
    r"^how to ",
    r"^why ",
    r"^what is ",
    r"^i ",
    r"^i'm ",
    r"^show ",
    r"^showcase ",
    r"^introducing ",
    r"^announcing ",
    r"^we ",
    r"^our ",
]
_TAG_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]{2,15}")


def _norm_item(it: dict) -> dict:
    """把 radar 输出的 item 标准化（不修改原对象）"""
    return {
        "title": (it.get("title") or "").strip(),
        "url": it.get("url", ""),
        "source": (it.get("source") or "").strip().lower(),
        "score": int(it.get("score", 0) or 0),
        "summary": (it.get("summary") or "").strip(),
        "tags": it.get("tags", []) or [],
    }


def _is_user_story(title: str) -> bool:
    """识别 HN / Reddit 上常见的'个人故事'标题，不适合做种草文案"""
    t = title.lower().strip()
    return any(re.match(pat, t) for pat in _USER_TITLE_PATTERNS)


def _extract_keywords(text: str, top_k: int = 8) -> list:
    """粗提取高频词（规则兜底时用）"""
    words = _TAG_RE.findall(text.lower())
    seen, out = set(), []
    for w in words:
        if w not in seen and len(w) > 2:
            seen.add(w)
            out.append(w)
        if len(out) >= top_k:
            break
    return out


def _by_rules(it: dict) -> dict:
    """无 LLM 时的兜底分析"""
    title = it["title"]
    summary = it["summary"]
    text = f"{title} {summary}"

    # 简单人群画像
    if any(k in title.lower() for k in ["developer", "dev", "code", "api", "framework"]):
        audience = "独立开发者 / 全栈工程师"
    elif any(k in title.lower() for k in ["ai", "gpt", "llm", "agent"]):
        audience = "AI 重度用户 / 内容创作者 / 创业者"
    elif any(k in title.lower() for k in ["saas", "tool", "platform"]):
        audience = "中小企业主 / 效率工具爱好者"
    elif any(k in title.lower() for k in ["shopify", "ecommerce", "store"]):
        audience = "跨境电商卖家"
    else:
        audience = "互联网从业者 / 工具控"

    is_story = _is_user_story(title)

    return {
        "angle": f"{title[:60]}（{it['source']}）的差异化价值" if not is_story else f"{title[:60]} 的真实用户故事拆解",
        "audience": audience,
        "pain_point": "信息爆炸但缺结构化、新鲜、可信的拆解" if not is_story else "同类人有同样的焦虑，想看到真实经历参考",
        "value_prop": "专业、可信、可直接复用的拆解 + 实操路径",
        "xhs_angle": (
            "❌ 这条不适合做小红书种草（属于个人叙事体）"
            if is_story
            else f"种草口吻：「用了 X，再也回不去 Y」+ 测评/对比"
        ),
        "zh_angle": (
            "✅ 知乎适合：叙述个人决策过程 + 复盘"
            if is_story
            else f"深度技术解析 + 同类工具横评 + 自用 SOP"
        ),
        "hashtags": _extract_keywords(text)[:6],
        "image_prompts": (
            [] if is_story
            else [
                f"hero image: {title[:80]}，现代极简，霓虹蓝紫渐变",
                f"对比图: before / after，使用场景",
            ]
        ),
        "is_story": is_story,
        "llm_used": "rules",
    }


# ===== LLM Provider 抽象 =====

def _call_openai(api_key: str, system_prompt: str, user_prompt: str) -> str:
    body = {
        "model": "gpt-4o-mini",
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 800,
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
            data = json.load(r)
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"OpenAI API error: {e.code} {e.read().decode()[:200]}")


def _call_deepseek(api_key: str, system_prompt: str, user_prompt: str) -> str:
    body = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 800,
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
            data = json.load(r)
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"DeepSeek API error: {e.code} {e.read().decode()[:200]}")


def _call_claude(api_key: str, system_prompt: str, user_prompt: str) -> str:
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 800,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=LLM_TIMEOUT) as r:
            data = json.load(r)
            return data["content"][0]["text"]
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Claude API error: {e.code} {e.read().decode()[:200]}")


# ===== JSON 解析（兼容 ```json 围栏）=====

def _extract_json(text: str) -> dict:
    text = text.strip()
    # 围栏
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # 第一段 {...}
    i, j = text.find("{"), text.rfind("}")
    if 0 <= i < j:
        text = text[i:j + 1]
    return json.loads(text)


# ===== 主入口 =====

_SYSTEM_PROMPT = """你是「商机挖掘 + 内容策略」双角色顾问。
输入一条英文或中文的「商机标题 / 摘要 / 来源」，输出一段 JSON。
要求：
- 用中文输出
- 角度可执行、不能空话
- 知乎和小红书的写法完全分开（避免同质化）
- is_story 字段识别：标题是"个人感受/故事"还是"工具/产品介绍"
- image_prompts 给出 2-3 张配图的中文描述（用于 AI 生图）
- 只输出 JSON，不要任何解释"""

_USER_PROMPT_TEMPLATE = """【商机】
title: {title}
source: {source}
score: {score}
summary: {summary}
tags: {tags}

【输出 JSON 字段】
{{
  "angle": "一句话切入角度（≤25 字）",
  "audience": "目标人群画像（一句话）",
  "pain_point": "这条商机解决的痛点",
  "value_prop": "用户视角的价值主张（≤30 字）",
  "xhs_angle": "小红书切入点（种草 / 测评 / 教程 / 反差 选一种，给具体思路）",
  "zh_angle": "知乎切入点（深度拆解 / 横评 / 复盘 / 教程 选一种，给具体思路）",
  "hashtags": ["3-6 个标签"],
  "image_prompts": ["2-3 张中文配图描述"],
  "is_story": true/false,
  "key_facts": ["2-3 条用于文案的事实点"]
}}"""


def analyze(item: dict) -> dict:
    """主入口：分析一条商机"""
    it = _norm_item(item)
    # 文本太短或空 → 直接走规则
    if not it["title"] and not it["summary"]:
        return {**_by_rules(it), "llm_used": "rules:empty"}

    # 选 provider
    provider = None
    api_key = None
    if (api_key := os.getenv("OPENAI_API_KEY")):
        provider, name = _call_openai, "openai"
    elif (api_key := os.getenv("DEEPSEEK_API_KEY")):
        provider, name = _call_deepseek, "deepseek"
    elif (api_key := os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")):
        provider, name = _call_claude, "claude"
    else:
        # 兜底
        result = _by_rules(it)
        return result

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        title=it["title"],
        source=it["source"],
        score=it["score"],
        summary=it["summary"],
        tags=",".join(it["tags"]) if it["tags"] else "",
    )
    try:
        raw = provider(api_key, _SYSTEM_PROMPT, user_prompt)
        parsed = _extract_json(raw)
        # 兜底字段
        parsed.setdefault("is_story", _is_user_story(it["title"]))
        parsed["llm_used"] = name
        return parsed
    except Exception as e:
        # LLM 挂掉降级
        result = _by_rules(it)
        result["llm_used"] = f"rules:fallback ({name} failed)"
        result["llm_error"] = str(e)[:120]
        return result


if __name__ == "__main__":
    import sys
    sample = {
        "title": sys.argv[1] if len(sys.argv) > 1 else "Cursor launches Agent Mode for autonomous coding",
        "url": "https://cursor.com",
        "source": "hackernews",
        "score": 88,
        "summary": "AI code editor Cursor now supports autonomous agent that can read/write whole project.",
        "tags": ["hot", "demand"],
    }
    result = analyze(sample)
    print(json.dumps(result, ensure_ascii=False, indent=2))
