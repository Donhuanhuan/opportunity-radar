"""3 Agent 协作编排器

执行流：
  M1 抓商机 → 写商机池
      ↓
  content_strategist（选 Top 3 + 定平台） ─── ¥0.01
      ↓
  formatter（3 标题 + 润色正文 + 配图 prompt）── ¥0.02
      ↓
  risk_monitor（合规扫描）                    ─── ¥0.005
      ↓
  写飞书「内容审核表」状态="待审"
      ↓
  欢欢审核 → 改"通过"
      ↓
  AuditGate → local_publisher → 发布

LLM 策略（按成本/质量自动选）：
  1. DeepSeek（首选，便宜）
  2. Claude（DeepSeek 失败时降级，写作最好）
  3. OpenAI（兜底，最贵）
  4. rules 模板（全部失败时）

CLI：
  python -m agents.orchestrator --dry-run
  python -m agents.orchestrator --limit 3
"""
import json
import os
import time
from pathlib import Path
from typing import List, Optional

import yaml

from radar.config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BITABLE_APP_TOKEN,
    DRAFTS_BITABLE_TABLE_ID,
)
from radar.publish.feishu_audit import SCHEMA as AUDIT_SCHEMA


AGENTS_DIR = Path(__file__).parent
COST_LOG = Path("data/agent_cost.jsonl")


# ===== LLM 调度 =====
def get_llm_chain():
    """按可用性优先级返回 LLM 客户端列表"""
    chain = []
    if os.getenv("DEEPSEEK_API_KEY"):
        chain.append(("deepseek", "deepseek-chat", "https://api.deepseek.com/v1"))
    if os.getenv("ANTHROPIC_API_KEY"):
        chain.append(("claude", "claude-3-5-haiku-latest", None))
    if os.getenv("OPENAI_API_KEY"):
        chain.append(("openai", "gpt-4o-mini", None))
    return chain


def llm_call(prompt: str, system: str = "", json_mode: bool = True, max_tokens: int = 2000) -> Optional[str]:
    """自动选 LLM 调用。返回 None 表示全部失败（降级到模板）"""
    import requests
    chain = get_llm_chain()
    if not chain:
        print("  ⚠ 无任何 LLM key，降级到 rules 模板")
        return None

    for provider, model, base_url in chain:
        try:
            if provider == "deepseek":
                r = requests.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system or "你是 AI 助手"},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"} if json_mode else None,
                    },
                    timeout=60,
                )
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                _log_cost(provider, model, max_tokens)
                return content

            elif provider == "claude":
                r = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": os.getenv("ANTHROPIC_API_KEY"),
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": max_tokens,
                        "system": system or "你是 AI 助手",
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=60,
                )
                r.raise_for_status()
                content = r.json()["content"][0]["text"]
                _log_cost(provider, model, max_tokens)
                return content

            elif provider == "openai":
                r = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system or "你是 AI 助手"},
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"} if json_mode else None,
                    },
                    timeout=60,
                )
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                _log_cost(provider, model, max_tokens)
                return content
        except Exception as e:
            print(f"  ⚠ {provider} 调用失败：{str(e)[:100]}，降级到下一个")
            continue
    return None


def _log_cost(provider: str, model: str, tokens: int):
    """记录 LLM 成本（估算）"""
    cost_table = {
        "deepseek-chat": 0.000001,        # ¥0.001/千token ≈ ¥0.001/1k = ¥0.000001/tok
        "claude-3-5-haiku-latest": 0.008,  # ~¥0.008/千tok (input+output 混合)
        "gpt-4o-mini": 0.0015,            # ~¥0.0015/千tok
    }
    cost = tokens * cost_table.get(model, 0.005) / 1000
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with COST_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.time(),
            "provider": provider,
            "model": model,
            "tokens": tokens,
            "cost_cny": round(cost, 6),
        }, ensure_ascii=False) + "\n")


# ===== Agent 加载 =====
def load_agent(name: str) -> dict:
    with (AGENTS_DIR / f"{name}.yaml").open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def render_template(template: str, **kwargs) -> str:
    for k, v in kwargs.items():
        template = template.replace("{" + k + "}", str(v))
    return template


# ===== Agent 调用 =====
def run_strategist(opportunities: List[dict], dry_run: bool = False) -> dict:
    """内容策略师：选 Top 3 + 定平台"""
    agent = load_agent("content_strategist")
    prompt = render_template(
        agent["llm_prompt_template"],
        opportunities=json.dumps(opportunities[:5], ensure_ascii=False, indent=2),
    )
    response = llm_call(prompt, system=agent["description"], json_mode=True)
    if response is None:
        # 降级：选评分最高的 3 条
        return {
            "picks": [
                {
                    "draft_id": op.get("draft_id", op.get("url", "")),
                    "platform": "xiaohongshu" if i < 2 else "zhihu",
                    "angle": op.get("title", "")[:30],
                    "target_audience": "通用",
                    "title_direction": ["A", "B", "C"],
                }
                for i, op in enumerate(sorted(opportunities, key=lambda x: x.get("score", 0), reverse=True)[:3])
            ],
            "rejected": [],
            "_fallback": True,
        }
    return json.loads(response)


def run_formatter(pick: dict, raw_draft: dict, dry_run: bool = False) -> dict:
    """排版师：3 标题 + 润色"""
    agent = load_agent("formatter")
    prompt = render_template(
        agent["llm_prompt_template"],
        platform=pick["platform"],
        raw_draft=json.dumps(raw_draft, ensure_ascii=False),
    )
    response = llm_call(prompt, system=agent["description"], json_mode=True)
    if response is None:
        return {
            "title_candidates": [
                {"label": "A", "text": raw_draft.get("title", "")},
                {"label": "B", "text": raw_draft.get("title", "") + "（揭秘）"},
                {"label": "C", "text": raw_draft.get("title", "") + "（亲测）"},
                {"label": "推荐", "text": raw_draft.get("title", "")},
            ],
            "body_final": raw_draft.get("body", ""),
            "image_prompts": [],
            "tags": raw_draft.get("tags", []),
            "_fallback": True,
        }
    return json.loads(response)


def run_risk_monitor(platform: str, title: str, body: str, dry_run: bool = False) -> dict:
    """风控监控：合规扫描"""
    agent = load_agent("risk_monitor")
    prompt = render_template(
        agent["llm_prompt_template"],
        platform=platform,
        title=title,
        body=body[:1000],
    )
    response = llm_call(prompt, system=agent["description"], json_mode=True, max_tokens=500)
    if response is None:
        return _simple_compliance_check(title, body)
    return json.loads(response)


def _simple_compliance_check(title: str, body: str) -> dict:
    """规则兜底：hard block + soft warn 关键词扫描"""
    hard_block = ["治愈", "根治", "稳赚", "无风险", "保证有效", "第一", "唯一", "最好"]
    soft_warn = ["据说", "网友说", "碾压", "秒杀", "吊打", "yyds"]
    text = f"{title} {body}"

    for kw in hard_block:
        if kw in text:
            return {
                "verdict": "block",
                "issues": [{"type": "hard", "quote": kw, "rule": "硬红线"}],
                "suggestion": f"删除或改写「{kw}」",
            }
    issues = []
    for kw in soft_warn:
        if kw in text:
            issues.append({"type": "soft", "quote": kw, "rule": "夸张用语"})
    return {
        "verdict": "warn" if issues else "pass",
        "issues": issues,
        "suggestion": "建议改写夸张词" if issues else "",
    }


# ===== 写飞书审核表 =====
def write_to_audit_table(pick: dict, formatted: dict, risk: dict) -> Optional[str]:
    """写入飞书审核表，返回 record_id"""
    from radar.notify.feishu_bitable import BitableClient

    client = BitableClient(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        app_token=FEISHU_BITABLE_APP_TOKEN,
    )

    fields = {
        "草稿ID": pick["draft_id"],
        "商机标题": pick.get("opportunity_title", ""),
        "商机链接": pick.get("opportunity_url", {}),
        "平台": pick["platform"],
        "标题": formatted.get("title_candidates", [{}])[-1].get("text", ""),
        "正文": formatted.get("body_final", ""),
        "标签": formatted.get("tags", []),
        "状态": "待审",
        "审核备注": f"risk: {risk.get('verdict', 'pass')}",
        "生成时间": int(time.time() * 1000),
    }

    try:
        record = client.create_record(DRAFTS_BITABLE_TABLE_ID, fields)
        return record.get("record_id", "")
    except Exception as e:
        print(f"  ⚠ 写飞书失败：{e}")
        return None


# ===== 主入口 =====
def run_pipeline(dry_run: bool = False, limit: int = 3) -> dict:
    """主入口：M1 抓 → 策略 → 排版 → 风控 → 写审核表"""
    # 1. 读 M1 商机
    opp_file = Path("data/opportunities.jsonl")
    if not opp_file.exists():
        return {"error": f"{opp_file} 不存在，请先跑 M1"}

    opportunities = []
    for line in opp_file.read_text(encoding="utf-8").splitlines()[:limit]:
        if line.strip():
            opportunities.append(json.loads(line))

    if not opportunities:
        return {"error": "无商机数据"}

    print(f"→ 读到 {len(opportunities)} 条商机")

    # 2. 策略师选 Top 3
    print("→ content_strategist 选题...")
    picks = run_strategist(opportunities, dry_run)
    print(f"  选了 {len(picks.get('picks', []))} 条")

    results = []
    for pick in picks.get("picks", []):
        # 3. 找对应商机作为 raw_draft
        raw = next((o for o in opportunities if o.get("draft_id") == pick["draft_id"] or o.get("url") == pick["draft_id"]), {})
        if not raw:
            raw = {"title": pick.get("angle", ""), "body": pick.get("angle", "")}

        # 4. formatter
        print(f"→ formatter 润色 [{pick['platform']}]...")
        formatted = run_formatter(pick, raw, dry_run)

        # 5. 风控
        print(f"→ risk_monitor 合规扫描...")
        title = formatted.get("title_candidates", [{}])[-1].get("text", "")
        risk = run_risk_monitor(pick["platform"], title, formatted.get("body_final", ""), dry_run)

        if risk.get("verdict") == "block":
            print(f"  ✗ 合规 block：{risk.get('suggestion', '')}")
            continue

        # 6. 写飞书审核表
        if dry_run:
            print(f"  [DRY-RUN] 跳过写飞书")
            results.append({"pick": pick, "formatted": formatted, "risk": risk})
        else:
            record_id = write_to_audit_table(pick, formatted, risk)
            results.append({"pick": pick, "formatted": formatted, "risk": risk, "record_id": record_id})

    return {
        "ts": time.time(),
        "picks_count": len(picks.get("picks", [])),
        "results": results,
        "dry_run": dry_run,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="3 Agent 编排器")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    result = run_pipeline(dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:2000])


if __name__ == "__main__":
    main()