"""商机雷达配置（可通过 .env 覆盖）"""
import os
from pathlib import Path

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ===== 信号源开关 =====
SOURCES = os.getenv("RADAR_SOURCES", "hackernews,github_trending,producthunt,kr36,weibo").split(",")

# ===== 过滤关键词（命中加分）=====
KEYWORDS_HOT = os.getenv("KEYWORDS_HOT", "AI,SaaS,出海,跨境,短视频,数字人,工具,自动化,赚钱,副业").split(",")
KEYWORDS_DEMAND = os.getenv("KEYWORDS_DEMAND", "效率,提效,降本,变现,赚钱,省时间").split(",")
KEYWORDS_BLOCK = os.getenv("KEYWORDS_BLOCK", "赌博,博彩,传销,虚拟币,资金盘,黄,赌,毒").split(",")

# ===== 通知渠道 =====
NOTIFY_CHANNELS = os.getenv("NOTIFY_CHANNELS", "feishu").split(",")

# ===== 飞书机器人 =====
FEISHU_WEBHOOK = os.getenv("FEISHU_WEBHOOK", "")

# ===== 邮件 =====
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.qq.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")

# ===== 输出条数 =====
TOP_N = int(os.getenv("TOP_N", "15"))

# ===== User-Agent =====
HEADERS = {
    "User-Agent": "Mozilla/5.0 (OpportunityRadar/1.0; +https://github.com/opportunity-radar)",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}