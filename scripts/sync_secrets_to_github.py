"""将本地 .env 中 workflow 引用的密钥同步到 GitHub Actions secrets。

用法:
  python scripts/sync_secrets_to_github.py            # 预览（列出将写入哪些 key）
  python scripts/sync_secrets_to_github.py --apply    # 实际写入
"""
import base64
import json
import os
import re
import sys
import urllib.request

import nacl.bindings
import nacl.encoding
import nacl.public
import nacl.secret
import nacl.utils

REPO = "Donhuanhuan/opportunity-radar"
# workflow(.github/workflows/radar.yml) 引用的全部 secret 名
SECRET_NAMES = [
    "FEISHU_APP_ID", "FEISHU_APP_SECRET",
    "FEISHU_AUDIT_APP_TOKEN", "FEISHU_AUDIT_TABLE_ID",
    "FEISHU_BITABLE_APP_TOKEN", "FEISHU_BITABLE_TABLE_ID",
    "DRAFTS_BITABLE_APP_TOKEN", "DRAFTS_BITABLE_TABLE_ID",
    "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
]


def get_token() -> str:
    # 从 git remote url 提取内嵌 token（避免明文出现在命令行）
    out = os.popen("git remote get-url origin").read().strip()
    m = re.search(r"https://[^:]+:([^@]+)@", out)
    if not m:
        sys.exit("无法从 git remote 提取 token")
    return m.group(1)


def _req(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main() -> None:
    apply = "--apply" in sys.argv
    token = get_token()

    # 读本地 .env
    env = {}
    for line in open(".env", encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

    # 现有远端 secrets
    cur = _req("GET", f"https://api.github.com/repos/{REPO}/actions/secrets", token)
    existing = {s["name"] for s in cur.get("secrets", [])}

    pub = _req("GET", f"https://api.github.com/repos/{REPO}/actions/secrets/public-key", token)
    pub_key = nacl.public.PublicKey(pub["key"], encoder=nacl.encoding.Base64Encoder)

    print(f"{'名称':<32} 本地  远端  动作")
    pending = []
    for name in SECRET_NAMES:
        val = env.get(name, "")
        has_local = bool(val)
        has_remote = name in existing
        action = "--"
        if has_local and (not has_remote or name not in existing or True):
            # 本地有值就写入（覆盖旧值，保证与本地一致）
            pending.append((name, val))
            action = "写入/更新" if has_remote else "新增"
        elif not has_local:
            action = "跳过(本地无)"
        print(f"{name:<32} {'有' if has_local else '无':<4} {'有' if has_remote else '无':<4} {action}")

    if not apply:
        print("\n[DRY-RUN] 加 --apply 实际写入")
        return

    for name, val in pending:
        box = nacl.public.SealedBox(pub_key)
        encrypted = box.encrypt(val.encode("utf-8"))
        payload = {
            "encrypted_value": base64.b64encode(encrypted).decode(),
            "key_id": pub["key_id"],
        }
        _req("PUT", f"https://api.github.com/repos/{REPO}/actions/secrets/{name}",
             token, payload)
        print(f"  ✓ {name} 已写入")

    # 复核
    cur2 = _req("GET", f"https://api.github.com/repos/{REPO}/actions/secrets", token)
    print("\n远端现有 secrets:", sorted(s["name"] for s in cur2.get("secrets", [])))


if __name__ == "__main__":
    main()
