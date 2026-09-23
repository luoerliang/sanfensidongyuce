# 三分六合彩 Webhook修复版 v11

修复你截图中的：
`ModuleNotFoundError: No module named 'telegram'`

原因：上一版 Webhook 改造时旧的 `from telegram import Update` 仍残留在 app.py，
但 requirements 已经移除了 python-telegram-bot。

v11 已彻底删除 python-telegram-bot 和所有 long polling / getUpdates 代码，
只使用 `requests + Telegram Bot API Webhook`。

## 部署后正常日志
应看到：
`[TG] setWebhook url=https://...onrender.com/telegram/webhook -> 200 ...`

收到开奖：
`[TG-WEBHOOK] parsed issue=...`
`[TG-WEBHOOK] inserted issue=...`

## Render 环境变量
BOT_TOKEN = 当前 Token
ALLOWED_CHAT_ID = -5560268424
DB_PATH = history.db

一般不需要 WEBHOOK_BASE_URL。
程序优先读取 Render 自动变量，识别失败时才手动填：
`WEBHOOK_BASE_URL=https://你的服务名.onrender.com`

## 保留功能
自适应动态换码、22码一键复制、4肖4码同屏、开奖结果、红蓝绿号码、
近60期回测命中率/错误率、历史滚动、/id、/status。
