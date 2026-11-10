# logs/runs.jsonl（运行日志，可选模块）

每行一个 JSON，由 `lib/runlog/runlog.py` 写入。每次运行两行：开始一行，结束一行；同一个 `run_id` 以最后一行为准。
以下是虚构样例。

```json
{"run_id":"r20261110-093000-a1b2","routine":"早报","status":"running","start":"2026-11-10T09:30:00+08:00"}
{"run_id":"r20261110-093000-a1b2","routine":"早报","status":"partial","start":"2026-11-10T09:30:00+08:00","end":"2026-11-10T09:41:12+08:00","secs":672,"aisa_calls":38,"cost_usd":0.214,"outputs":12,"pushed":true,"sources":{"producthunt":"ok","reddit":"fail:429"},"error":"reddit 被限速，本次跳过"}
```

`status`：`running` → `ok` / `partial` / `fail` / `skipped`

# logs/approvals.jsonl

```json
{"ts":"2026-11-10T14:02:00+08:00","kind":"spend","ask":"查 300 个域名的外链，约 3 美元","answer":"同意","run_id":"r20261110-140000-c3d4"}
```

`kind`：`spend` / `send` / `delete` / `other`
