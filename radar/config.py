"""商机雷达配置（可通过 .env 覆盖）"""
import os
from pathlib import Path

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def _env(key: str, default: str = "") -> str:
    """读取环境变量；GitHub Actions 会把未配置 secret 传成空串，这里回退默认"""
    v = os.getenv(key)
    return v if v not in (None, "") else default


def _env_int(key: str, default: int) -> int:
    """读取整型环境变量，空串/非法值回退默认"""
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


# ===== 信号源开关 =====
SOURCES = _env("RADAR_SOURCES", "hackernews,github_trending,producthunt,kr36,weibo").split(",")

# ===== 过滤关键词（命中加分）=====
KEYWORDS_HOT = _env("KEYWORDS_HOT", "AI,SaaS,出海,跨境,短视频,数字人,工具,自动化,赚钱,副业").split(",")
KEYWORDS_DEMAND = _env("KEYWORDS_DEMAND", "效率,提效,降本,变现,赚钱,省时间").split(",")
KEYWORDS_BLOCK = _env("KEYWORDS_BLOCK", "赌博,博彩,传销,虚拟币,资金盘,黄,赌,毒").split(",")

# ===== 通知渠道 =====
NOTIFY_CHANNELS = _env("NOTIFY_CHANNELS", "feishu").split(",")

# ===== 飞书机器人 =====
FEISHU_WEBHOOK = _env("FEISHU_WEBHOOK", "")

# ===== 飞书多维表格（商机池）=====
# 飞书自建应用凭证 → https://open.feishu.cn/app
FEISHU_APP_ID = _env("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = _env("FEISHU_APP_SECRET", "")
# 多维表格 URL 形如 https://xxx.feishu.cn/base/APP_TOKEN?table=TABLE_ID
FEISHU_BITABLE_APP_TOKEN = _env("FEISHU_BITABLE_APP_TOKEN", "")
FEISHU_BITABLE_TABLE_ID = _env("FEISHU_BITABLE_TABLE_ID", "")

# ===== 邮件 =====
EMAIL_HOST = _env("EMAIL_HOST", "smtp.qq.com")
EMAIL_PORT = _env_int("EMAIL_PORT", 465)
EMAIL_USER = _env("EMAIL_USER", "")
EMAIL_PASS = _env("EMAIL_PASS", "")
EMAIL_TO = _env("EMAIL_TO", "")

# ===== 输出条数 =====
TOP_N = _env_int("TOP_N", 15)

# ===== User-Agent =====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (OpportunityRadar/1.0; +https://github.com/opportunity-radar)",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}