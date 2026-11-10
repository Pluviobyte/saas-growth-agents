# 新词监控 Bot：岗位说明

每天早、中、晚三次播报新出现、可被搜索的词：AI 新产品、新模型、新梗、新模板。播报前一小时先预跑采集，夜里再补采一次。

这是作者实际在跑的流水线，代码量最大（约 4000 行），装好后基本不用改。

## 安装

在 Bot 的云电脑里：

```bash
git clone https://github.com/Pluviobyte/saas-growth-agents.git
bash saas-growth-agents/bots/newterm/install.sh /workspace/newterm
```

然后把 Key 从保险库写进 `/workspace/newterm/.env`。必填 `AISA_API_KEY`，其余可选：

| 变量 | 用途 | 没有会怎样 |
|---|---|---|
| `AISA_API_KEY` | Google Trends 打分、TikTok 搜索、SERP | 必填 |
| `AISA_KEY_A` / `AISA_KEY_B` | 两个 Key 轮流用，分摊限速 | 只用一个 Key |
| `GEFEI_API_KEY` | 哥飞新词服务（seo.web.cafe，付费） | 跳过这个词源 |
| `PRODUCTHUNT_TOKEN` | Product Hunt GraphQL | 退回 Atom 订阅 |
| `GH_TOKEN` | GitHub API 兜底 | 只抓 Trending 页面 |

## 发给 Bot 的岗位说明

装好后先让 Bot 读 `bots/newterm/skills/getting-started/SKILL.md`，它会一次问一个问题，问完自己建例程。
播报格式、门槛、去重规则都在 `bots/newterm/skills/newterm-monitor/SKILL.md`，建议把两个技能都存进 Bot 的技能里。

想自己写岗位说明的话，核心就这几句：

```text
你是我的新词监控员。工作目录 /workspace/newterm，Key 在 .env 里（从保险库写入，不要打印）。
预跑例程只采集不说话；播报例程先运行 python3 broadcast_ready.py <slot> --timeout 600 等预跑完成，
再读 prescan_<日期>_<slot>/ 下的 report.md、radar.md、tiktok.json，按 newterm-monitor 技能的格式写中文播报。
只报没推过的词，推过的记进 pushed.json。午报没有新词就不说话。
数据源报错或预跑超时要在播报开头一行说明，不能当作「今天没有新词」。
```

## 词源

| 词源 | 脚本 | 进播报的条件 |
|---|---|---|
| Google Trends 词根上升 | `newterm.py` | 热度 ≥ GPTs × 0.2 |
| TikTok / X 爆款梗 | `tiktok_scan.py` | ≥ GPTs × 0.05 正式推，低于的进「早期观察」 |
| 竞品 sitemap 新页面 | `radar_sitemaps.py` | 新内页且词没推过，不看热度 |
| 付费导航站新上架 | `radar_paid_nav.py` | 首次出现 |
| Product Hunt | `radar_producthunt.py` | 首次出现 |
| GitHub Trending | `radar_github_trending.py` | 首次出现 |
| Reddit | `radar_reddit.py` | 首次出现 + 去噪 |
| CapCut 模板 | `radar_capcut.py` | 首次出现 |
| 哥飞新词（可选） | `gefei_api.py` | 「值得做 / 可以试试」且热度 ≥ × 0.2 |

竞品 sitemap 和导航站这两个词源要盯哪些站，仓库里不带名单，每个人的赛道不一样。装好后让 Bot 问你的赛道和几个主要竞品，照 `watchlist.example.json` 的格式写进工作目录的 `watchlist.json`；没填的话这两个词源会跳过，其他词源照常跑。`watchlist.json` 是你的个人数据，不要提交到公开仓库。
