"""本地发布器（路径B：agent-browser 半本机）

⚠️ 关键说明：本模块调用 `agent-browser` CLI（WorkBuddy 云端 daemon）。
它**不是**你本机浏览器，但 cookie 在 daemon 内持久化（关闭 daemon 后失效）。
"""
from .local_publisher import PublishTask, publish_xiaohongshu, publish_zhihu, preflight_check
from .audit_gate import AuditGate, AuditDecision

__all__ = [
    "PublishTask",
    "publish_xiaohongshu",
    "publish_zhihu",
    "preflight_check",
    "AuditGate",
    "AuditDecision",
]