# judgment-ledger.jsonl（交易雷达判断账本）

每行一个 JSON，由 `extras/trade-radar/scripts/ledger.py add` 写入，复盘时用 `resolve` 更新 `outcome`。
只记判断，不记仓位、订单、钱包：带这些字段的记录会被拒绝。

```json
{"id":"j20261109100000","ts":"2026-11-09T10:00:00+08:00","outcome":"pending","event":"演示事件","credibility":"已证实","attribution":"...","assets":["BTC"],"direction":"down","horizon_h":24,"levels":[77000,75000],"invalidation":"4 小时内收回 78000","confidence":0.6,"analogs":"...","materials":"materials/20261109-100000.json"}
```

`outcome`：`pending` → `hit` / `miss` / `partial` / `void`
