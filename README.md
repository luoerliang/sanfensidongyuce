# 三分六合彩 Webhook稳定版 v10

## 为什么改成 Webhook
v9 以前使用 Telegram `getUpdates` 长轮询。
Render 支持零停机部署，部署新版本时新旧实例可能短暂并存，
两个实例同时 `getUpdates` 就会出现：

`telegram.error.Conflict: terminated by other getUpdates request`

v10 完全移除 long polling，改用 Telegram Webhook。
Telegram 官方规定 getUpdates 与 webhook 是互斥的；Webhook 模式不会有两个实例抢 getUpdates 的冲突。

Render 会自动提供 `RENDER_EXTERNAL_URL`，程序自动设置：
`https://你的服务.onrender.com/telegram/webhook`

并使用 Telegram `secret_token` 校验 webhook 请求。

## 保留全部功能
- 官方开奖机器人消息自动入库
- 自适应动态换22码
- 22码一键复制
- 4肖4码同屏
- 最新开奖结果
- 红/蓝/绿号码颜色
- 近60期滚动回测命中率/错误率
- 历史列表在最下面可手滑滚动
- /id
- /status
- 波色不参与特码/4码评分

## Render 环境变量
BOT_TOKEN = 当前新 Token
ALLOWED_CHAT_ID = -5560268424
DB_PATH = history.db

不需要填写 Webhook URL。Render 自动提供 `RENDER_EXTERNAL_URL`。

## 部署后
日志应该看到：
`[TG] setWebhook -> 200 ... "Webhook was set"`

之后新期开奖会看到：
`[TG-WEBHOOK] parsed issue=...`
`[TG-WEBHOOK] inserted issue=...`

可访问 `/api/webhook` 查看 Telegram webhook 当前状态。
