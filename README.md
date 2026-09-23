# 三分六合彩 极速续存版 v13

这版专门解决两个问题：

## 1. 网页刷新慢
以前 `/api/prediction` 每次刷新都可能重新扫一万多期。
v13 改成：
- 启动时只算一次
- 每收到一个新期开奖才重算一次
- 结果放在内存缓存
- 网页每 1 秒只读取缓存

所以页面刷新不再每次重新跑模型。

## 2. 新版本要带上机器人后来收录的历史
v13 已内置你当前旧服务历史地址：

`https://sanfensidongyuce-2.onrender.com/api/history?limit=500`

新服务启动时自动：
1. 导入 ZIP 里的原始 14343 期
2. 从旧服务抓取机器人后来收录的最近 500 期
3. 按期号去重合并
4. 再开始新版本的 Telegram Webhook

从 v13 开始又增加：
- `/api/export?limit=20000`：完整历史导出（含全部生肖/颜色/raw）
- `/api/sync-status`：查看同步状态
- `/api/sync-history`：手动同步

这样下一版可以直接从 v13 的完整 `/api/export` 迁移，不必再回到最初 CSV。

## 最稳的部署方法（重要）
为了确保“旧服务”在新版本启动时还能提供历史数据：
- 不要直接覆盖 `sanfensidongyuce-2`
- 用 v13 新建一个 Render Web Service（例如 `sanfensidongyuce-3`）
- 环境变量照旧：
  - BOT_TOKEN
  - ALLOWED_CHAT_ID=-5560268424
  - DB_PATH=history.db
  - HISTORY_SOURCE_URL=https://sanfensidongyuce-2.onrender.com/api/history?limit=500
- 新服务显示历史总数和最新期号正确后，再暂停旧服务

## 长期真正不丢历史
Render 免费 Web Service 的本地 SQLite 不是永久存储。
v13 的“自动从上一版本迁移”可以让换版本时保留数据，但它不是数据库级永久保障。
要做到服务重启/换机器也绝不丢，最终应使用持久磁盘或 PostgreSQL。

其余功能全部保留：
- 波色/生肖/大小/单双走势特征
- 自适应22码
- 4肖对应每肖1~3码
- 22码一键复制
- 最新开奖结果
- 红蓝绿颜色
- 回测命中率/错误率
- 底部历史滚动
- Webhook稳定接收
