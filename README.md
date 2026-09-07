# 📡 商机雷达 (Opportunity Radar)

> 无人值守的互联网商机发现系统 · 每天 9:00 自动推送

**适用人群**：创业者 / 副业玩家 / 内容创作者 / 投资分析师

## ✨ 功能特性

- 🔭 **5 大信号源自动扫描**：HackerNews / GitHub Trending / Product Hunt / 36氪 RSS / 微博热搜
- 🎯 **智能打分**：关键词命中 + 热度值排序
- 🛡️ **内容过滤**：自动屏蔽违规关键词（赌博 / 传销 / 资金盘等）
- 📬 **多渠道推送**：飞书机器人 / 邮件（HTML 富文本）
- ⏰ **GitHub Actions 定时**：UTC 1:00 = 北京时间 9:00，无需服务器
- 💸 **完全免费**：跑在 GitHub 免费额度上

## 🚀 5 分钟部署

### 步骤 1：Fork 仓库

点击右上角 **Fork**，把仓库复制到你自己的 GitHub。

### 步骤 2：创建飞书机器人

1. 打开飞书群 → 群设置 → 群机器人 → 添加机器人 → 自定义机器人
2. 复制 Webhook URL

### 步骤 3：配置 Secrets

进入你 Fork 的仓库 → Settings → Secrets and variables → Actions → New repository secret

| Secret 名称 | 必填 | 示例 |
|---|---|---|
| `FEISHU_WEBHOOK` | ✅ | `https://open.feishu.cn/open-apis/bot/v2/hook/xxx` |
| `EMAIL_HOST` | ❌ | `smtp.qq.com` |
| `EMAIL_PORT` | ❌ | `465` |
| `EMAIL_USER` | ❌ | `your@qq.com` |
| `EMAIL_PASS` | ❌ | QQ 邮箱授权码 |
| `EMAIL_TO` | ❌ | `target@x.com` |

### 步骤 4：手动触发测试

进入 Actions → 商机雷达 → Run workflow → 选 `dry_run=true`

如果日志显示「抓取成功」，切换为 `dry_run=false` 触发真实推送。

### 步骤 5：等待第二天 9:00 自动运行

或修改 `.github/workflows/radar.yml` 中的 cron 表达式调整时间。

## 🧪 本地调试

```bash
# 克隆
git clone https://github.com/your/opportunity-radar.git
cd opportunity-radar

# 安装
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配置
cp .env.example .env
# 编辑 .env 填入 FEISHU_WEBHOOK

# 试跑（不推送）
python -m radar.scan --dry-run

# 完整跑
python -m radar.scan

# 只跑指定源
python -m radar.scan --source hackernews,weibo
```

## 📂 项目结构

```
opportunity-radar/
├── .github/workflows/radar.yml   # GitHub Actions 定时任务
├── radar/
│   ├── __init__.py
│   ├── scan.py                   # 主入口
│   ├── config.py                 # 配置（.env 加载）
│   ├── filters.py                # 关键词过滤 + 打分
│   ├── sources/
│   │   ├── hackernews.py         # HN Top Stories
│   │   ├── github_trending.py     # GitHub Trending
│   │   ├── producthunt.py        # PH 今日榜
│   │   ├── kr36.py               # 36氪 / 亿欧 / 机器之心 RSS
│   │   └── weibo.py              # 微博热搜
│   └── notify/
│       ├── feishu.py             # 飞书机器人
│       └── email.py              # 邮件 SMTP
├── scripts/                      # 预留脚本目录
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## ⚙️ 进阶配置

### 调整扫描关键词

编辑 `.env`：

```bash
KEYWORDS_HOT=AI,SaaS,出海,跨境,短视频,数字人
KEYWORDS_DEMAND=效率,提效,降本,变现
KEYWORDS_BLOCK=赌博,博彩,传销,虚拟币
```

### 添加新信号源

1. 在 `radar/sources/` 创建 `xxx.py`，实现 `fetch()` 函数
2. 在 `radar/sources/__init__.py` 中导出
3. 在 `radar/scan.py` 的 `SOURCE_MODULES` 中注册

```python
# radar/sources/zhihu.py
def fetch():
    return [{
        "source": "知乎热榜",
        "title": "...",
        "summary": "...",
        "url": "...",
        "score": 0,
        "comments": 0,
    }]
```

### 调整推送时间

编辑 `.github/workflows/radar.yml` 的 cron：

```yaml
schedule:
  - cron: '0 1 * * *'   # UTC 1:00 = 北京 9:00
```

> 在线转换：<https://crontab.guru/>

## 📊 输出样例

```markdown
📡 商机雷达日报 · 2026-09-07
共命中 15 条商机

1. Notion AI Slides                🔥 热门   HackerNews  238
2. ShipFast v3                     🔥 热门   PH          156
3. awesome-ai-tools                💰 变现   GitHub       89
4. AI数字人变现指南                💰 变现   微博热搜   1200000
...
```

## ⚠️ 风险提示

- ❌ 不要用于爬取用户隐私数据
- ❌ 不要高频调用（GitHub Actions 免费额度为 2000 分钟/月）
- ❌ 商业数据爬取前务必确认对方 robots.txt
- ✅ 所有推送由你本人配置触发，代码透明可审计

## 📜 License

MIT

---

🤖 由 [赚钱小能手作战手册](https://github.com/your/make-monney) 推荐