# 三分六合彩 智能稳定版 v4

v4 修复：
- 修复 Render 日志中的 `set_wakeup_fd only works in main thread`。
- Telegram polling 在后台线程运行时禁用 signal handlers。
- 使用 Gunicorn 运行 Web 服务，不再使用 Flask development server。
- Gunicorn 启动时自动初始化 SQLite、导入 history.csv、启动 Telegram worker。
- 保留 `/id`、`/status`、开奖消息解析、去重、22特码/4码/4肖动态模型。
- 波色不参与特码和4码评分。

## Render 环境变量
BOT_TOKEN = 你的机器人 Token
DB_PATH = history.db
ALLOWED_CHAT_ID 初次测试先不要设置。

## 部署后测试
私聊机器人：
/id
/status

如果 `/id` 和 `/status` 正常，再配置群组接收方式。

注意：`history.db` 在 Render 免费实例的普通文件系统中不是永久持久化存储；重新部署可能丢失部署后新增记录。确认功能正常后应迁移到持久化存储。
