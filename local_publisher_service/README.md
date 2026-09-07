# Local Content Publisher

本机内容发布服务，复用 Microsoft Edge 登录态，支持小红书/知乎自动发布。

## Quick Start

```bash
# 1. 安装依赖
.\install.cmd

# 2. 启动服务
.\start.cmd

# 3. 健康检查
curl http://localhost:19000/health
```

## API

### POST /publish

```json
{
  "platform": "xiaohongshu",
  "title": "标题",
  "body": "正文",
  "tags": ["AI", "副业"],
  "dryRun": false
}
```

### GET /health

```json
{
  "ok": true,
  "edge": true,
  "userData": true
}
```

## 安全提示

- 服务只监听 `127.0.0.1:19000`，外网无法访问
- 不存储任何密码/token，只复用浏览器用户数据
- 发布前建议 `dryRun: true` 做一次演练
