# 出海站点运营 Bot：装好后的验收

1. `python3 tests/test_dry_run.py` 全部 OK；`python3 lib/aisa/aisa_cli.py balance` 返回余额。
2. **问价**：`python3 lib/aisa/aisa_cli.py run --quote serp_google keyword="ai video generator"`，确认单次价格在你能接受的范围。
3. **找站**：给 Bot 一个你熟悉的词，确认 `sites.csv` 里出现的站和你手动搜的前几名大致一致，大站已被过滤。
4. **指标**：`own_sites.txt` 写进你的站，跑 `dr_check.py --own`，确认 DR 和 Ahrefs 网页上一致；第二天再跑，确认有 `delta`。
5. **提交**：建好一个产品卡，让 Bot「提交 2 个」，确认：真的成功了 2 个；付费 / 互链的被跳过并写了原因；`submit-log.jsonl` 每次尝试都有记录。
