# 三分时时彩智能稳定版 v3

修复：
- 修复缺少 `import csv` 导致 Render 启动失败。
- 默认数据库改为 `history.db`，不会因为不存在 `/var/data` 而启动失败。
- 自动清理旧 Telegram webhook 后启动 long polling。
- `/id` 返回当前聊天 Chat ID。
- `/status` 返回历史期数和最新期号。
- 自动导入 history.csv，已有数据库时不会重复导入。
- 新期开奖按期号去重并校验 7 个号码。

算法：
- 特码使用多时间尺度指数衰减、长期收缩、遗漏弱因子和弱正码上下文的集成评分。
- 4码和4肖使用独立多窗口衰减模型。
- 波色只保存，不进入特码/4码评分。
- 22个特码最终按数字升序显示。

Render：
1. 上传这些文件到 GitHub 仓库根目录。
2. Render 建 Web Service / Blueprint。
3. Environment 添加 BOT_TOKEN。
4. 初次测试时 ALLOWED_CHAT_ID 可以留空。
5. DB_PATH 保持 history.db。
6. 部署成功后私聊机器人 `/id`、`/status`。

注意：Render 非持久磁盘环境重新部署可能丢失运行期间新增的 SQLite 数据。确认程序稳定后，再迁移到持久数据库/磁盘。
彩票开奖结果具有随机性；本程序输出是历史统计候选，不保证命中。
