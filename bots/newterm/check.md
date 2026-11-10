# 新词监控 Bot：装好后的验收

1. `bash bots/newterm/install.sh /workspace/newterm` 没有报错，依赖装齐（`python3 -c "import pandas, pytrends, curl_cffi, bs4"`）。
2. 工作目录里有 `watchlist.json`，`sitemaps` 和 `paid_nav` 下填的是你自己赛道的站（不是示例域名）；`python3 /workspace/newterm/radar_sitemaps.py --out /tmp/wl --no-score --sites <其中一个站>` 能拉到网址。
3. `.env` 权限是 600，里面有 `AISA_API_KEY`；`python3 lib/aisa/aisa_cli.py balance` 返回余额。
4. 手动跑一次 `bash /workspace/newterm/prescan.sh morning`（约 10 到 30 分钟），结束后：
   - `prescan_<日期>_morning/completion.json` 里 `state` 是 `complete` 或 `partial`
   - `partial` 时看 `source_status.tsv` 哪个词源失败，失败原因要能在对应的 `.log` 里找到
5. `python3 /workspace/newterm/broadcast_ready.py morning --timeout 60` 返回 `ready` 或 `partial`。
6. 让 Bot 按技能格式写一次播报，确认：没有表格；每个词有热度（GPTs × N）、来源、是做什么的。
7. 第二天早报确认昨天推过的词没有重复出现（除非又过了门槛并标了「再推」）。
