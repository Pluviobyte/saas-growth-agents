# 新词监控 Bot：例程

时间都是 Asia/Shanghai。预跑只采集不说话，播报只汇总不重跑。

| 例程 | 时间 | 做什么 |
|---|---|---|
| 早间预跑 | 08:20 ±10 分钟 | 让 X 读最近的 AI 爆款贴写进 `prescan_<日期>_morning/tiktok_x_input.json`，再 `nohup bash prescan.sh morning &` |
| 早报 | 09:30 | `python3 broadcast_ready.py morning --timeout 600`，就绪后写播报 |
| 午间预跑 | 10:20 ±10 分钟 | 同上，slot 换成 noon（TikTok 不再打 Trends 分，省额度） |
| 午报 | 11:58 | 只报新词；没有就不说话 |
| 晚间预跑 | 16:20 ±10 分钟 | 同上，slot 换成 evening |
| 晚报 | 17:50 | 同早报 |
| 夜间采集 | 00:30、04:30 ±15 分钟 | `nohup bash night_collect.sh &`，不播报、不打分 |

## 省额度的设置（脚本里已经默认）

- `CACHE_TTL_H=18`、`ROOTS_TTL_H=24`：晚上复用早上的打分，不重复查 Trends
- 午间、晚间的 TikTok 扫描带 `--no-trends`
- 白天的 sitemap 扫描带 `--no-score`
- SERP 搜索量这类贵接口不放进每日例程

先跑一周，用 `python3 lib/aisa/aisa_cli.py balance` 看每天花多少，再决定要不要关掉某个词源。
