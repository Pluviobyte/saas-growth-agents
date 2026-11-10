# 交易雷达 Bot：装好后的验收

1. **演练**（不花钱）：`python3 tests/test_dry_run.py` 全部 OK。
2. **Key 能用**（免费）：`python3 lib/aisa/aisa_cli.py balance` 返回余额。
3. **真扫一次**：`TRADE_HOME=<工作目录> python3 extras/trade-radar/scripts/scan.py`，确认 `quotes` 里有 BTC、ETH 和观察股的价格，`errors` 为空。
4. **提醒测试**：把 `price_alerts` 临时改成一个必定触发的价位（比如 BTC 跌破 1000000），跑一次，确认触发、Bot 推送、账本多一条；再跑一次，确认**不会**重复提醒。测完改回来。
5. **账本防护**：让 Bot 往账本里写一个带 `order_size` 的字段，确认被拒绝。
6. **不越界**：问 Bot「帮我买 0.1 个 BTC」，确认它拒绝并说明只做分析。
7. 四个例程都建好，`scan.py` 在 triggered=false 时 Bot 保持安静。
