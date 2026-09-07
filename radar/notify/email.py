"""邮件推送（SMTP）"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from radar.config import EMAIL_HOST, EMAIL_PORT, EMAIL_USER, EMAIL_PASS, EMAIL_TO


def build_html(items: list) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    rows = ""
    for i, it in enumerate(items, 1):
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee">{i}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">
            <a href="{it.get('url','#')}" style="color:#1a73e8;text-decoration:none">
              {it.get('title','')}
            </a>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:#666">{it.get('source','')}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:#999">{it.get('score',0)}</td>
        </tr>"""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>商机雷达日报 {today}</title></head>
<body style="font-family:-apple-system,sans-serif;max-width:760px;margin:0 auto;padding:20px">
<h2 style="color:#22c55e">📡 商机雷达日报 · {today}</h2>
<p style="color:#666">共命中 {len(items)} 条商机</p>
<table style="width:100%;border-collapse:collapse;margin-top:16px">
  <thead>
    <tr style="background:#f5f5f5">
      <th style="padding:8px;text-align:left">#</th>
      <th style="padding:8px;text-align:left">标题</th>
      <th style="padding:8px;text-align:left">来源</th>
      <th style="padding:8px;text-align:left">Score</th>
    </tr>
  </thead>
  <tbody>{rows}</tbody>
</table>
<p style="color:#999;font-size:12px;margin-top:24px">商机雷达 v1.0 · GitHub Actions 自动生成</p>
</body></html>"""


def send_daily(items: list) -> bool:
    if not all([EMAIL_USER, EMAIL_PASS, EMAIL_TO]):
        print("[Email] 配置缺失，跳过")
        return False
    if not items:
        print("[Email] 无内容，跳过")
        return False

    msg = MIMEMultipart("alternative")
    today = datetime.now().strftime("%Y-%m-%d")
    msg["Subject"] = f"📡 商机雷达日报 {today}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(build_html(items), "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(EMAIL_HOST, EMAIL_PORT, timeout=10) as s:
            s.login(EMAIL_USER, EMAIL_PASS)
            s.sendmail(EMAIL_USER, EMAIL_TO.split(","), msg.as_string())
        print("[Email] 推送成功")
        return True
    except Exception as e:
        print(f"[Email] 推送异常: {e}")
        return False