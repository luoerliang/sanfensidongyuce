# 三分六合彩 智能稳定版 v5

本版针对“机器人正常、网页正常，但官方开奖不入库”的问题修复。

## v5 关键修复
- 修复 `01`、`03`、`05` 等带前导零号码无法解析的问题。
- 支持 01~09、1~9、10~49。
- Render 日志会明确显示：是否收到 TG 消息、发送者是不是机器人、解析出的期号和7码、是否成功入库。
- 对官方机器人消息只入库、不自动回复，避免 bot-to-bot 回复循环。
- 保留 v4 的 Gunicorn、/id、/status、动态22特码、4码、4肖、波色独立逻辑。

## Render 环境变量
- BOT_TOKEN = 你的新 Token
- DB_PATH = history.db
- ALLOWED_CHAT_ID = -5560268424  （你的开奖群 Chat ID；可以填上）

部署后等下一期开奖，Render Logs 正常应看到：
`[TG] ... is_bot=True ...`
`[TG] parsed issue=... nums=[...]`
`[TG] inserted issue=...`

然后网页历史期数会增加，最新期号、22码、4码、4肖会刷新。
