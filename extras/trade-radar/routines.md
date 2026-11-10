# 交易雷达 Bot：例程

| 例程 | 时间（Asia/Shanghai） | 做什么 | 什么时候说话 |
|---|---|---|---|
| 价格扫描 | 每 15 分钟 | `scan.py --no-keywords` | 触发才说 |
| 事件扫描 | 每小时 | `scan.py`（含 X 关键词） | 触发才说 |
| 复盘 | 每天 23:00 | `ledger.py due` → 逐条查走势 → `ledger.py resolve` | 有到期判断才说 |
| 周统计 | 每周日 21:00 | `ledger.py stats --days 7` + 提示词修改建议 | 每周一次 |

扫描类例程的说明可以写成：

```text
运行 TRADE_HOME=<工作目录> python3 <仓库目录>/extras/trade-radar/scripts/scan.py --no-keywords。
triggered=false 且 errors 为空：保持安静，不发任何消息。
triggered=true：按岗位说明分析并决定是否推送。errors 不为空：告诉我哪个接口出了什么错。
```

额度参考：价格扫描每次 1 到 2 个 AIsa 调用；带关键词的扫描每条 X 查询多 1 个调用。先跑一周，看 `aisa_cli.py balance` 的消耗再调频率。
