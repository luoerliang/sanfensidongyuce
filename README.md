# 澳门三分彩 TG 自动接收版（Render 一键部署）

这个版本专门为 iPhone + Render 做了简化：
- 不再需要 `templates` 文件夹
- 页面直接内置在 `app.py`
- 自带 `render.yaml`
- 数据库默认使用 `/var/data/history.db`
- 保留 `history.csv` 作为初始历史数据
- Telegram 消息自动解析期号、7号码、7生肖、7波色
- 自动去重并重新计算 22特码、4码、4肖
- 波色不参与特码和4码评分

## 最简单部署方式

### 方式 A：上传到 GitHub
解压这个 ZIP 后，GitHub 仓库根目录直接上传这些文件：
app.py
Dockerfile
requirements.txt
render.yaml
history.csv
.env.example
README.md

注意：这个版本没有任何子文件夹。

### 方式 B：Render
Render -> New -> Blueprint
连接 GitHub 仓库，Render 会读取 `render.yaml`。
部署后，在服务 Environment 中填写：
BOT_TOKEN = 你的 Telegram Bot Token
ALLOWED_CHAT_ID = 开奖群组 chat_id

不要把 Token 写入 GitHub。

## Telegram
机器人必须加入开奖群组，并按 Telegram 的 Bot-to-Bot/Privacy Mode 规则配置，确保能看到官方开奖机器人的消息。

## 消息格式
例如：
澳门三分彩第:20260923435期开奖结果:
25 27 18 30 35 44 11
馬 龍 牛 牛 猴 豬 猴
🔵 🟢 🔴 🔴 🔴 🟢 🟢

程序按前6个号码为正码、最后一个为特码。
