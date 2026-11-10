# 运行日志（可选模块）

> ⚠️ **会多消耗 Bot 的额度，按需开启，默认不开。**
> 开了以后，每次例程要多跑一两条命令，每晚总结前还要多读一次体检结果。这些都算 Bot 自己的额度（Grok Bot 这类产品按周给的对话和运行额度），例程越多、越频繁，多出来的就越多。
> AIsa 不会多花钱：日志只在本地写文件，不调用任何接口。

业务账本（提交记录、判断账本、知识库索引）记的是「做出了什么」。运行日志记的是「系统自己怎么样」：例程有没有漏跑、跑一半有没有挂、花了多少、推送发出去没有、你批准过什么、规则什么时候被改过。出了问题不用翻聊天记录，聊天记录会被压缩，也看不出趋势。

## 三本日志

都放在 `RUNLOG_HOME`（建议 `<工作目录>/logs`）：

| 文件 | 每行记什么 | 保留多久 |
|---|---|---|
| `runs.jsonl` | 每次例程两行：开始一行 `status=running`；结束一行写最终状态（`ok` / `partial` / `fail` / `skipped`）、耗时、AIsa 调用次数和花费、产出几条、推送没有、各数据源成败、报错摘要 | 90 天，过期按月压缩进 `archive/` |
| `approvals.jsonl` | 每次请示花钱、对外发送、删除：问了什么、你怎么回的、什么时候 | 永久 |
| `rules-changelog.md` | 每次按你的纠正改技能、例程或长期指令：改了什么、为什么、改之前的原文 | 永久 |

字段格式见 [templates/runs.schema.jsonl.md](../../templates/runs.schema.jsonl.md)。写入前统一打码，Key、Token、Cookie、密码一律换成 `***`。

## 选一档开

| 档位 | 包含 | 额度消耗 |
|---|---|---|
| **轻量** | 只记审批和规则变更 | 几乎不增加，只在请示和改规则时多一条命令 |
| **标准** | 轻量 + 每次例程记运行日志 | 每次例程多一两条命令 |
| **完整** | 标准 + 每晚体检、每周归档 | 再加上每晚读一次体检结果、每周一条归档命令 |

想要稳定、出了问题能查到原因，选「完整」；额度紧就先开「轻量」，跑稳了再往上加。

## 怎么开

在工作目录的 `.env`（或 Bot 的保险库 / 环境变量）里加两行：

```bash
RUNLOG_HOME=<工作目录>/logs
AISA_CALL_LOG=<工作目录>/logs/aisa-calls.log
```

第二行让 AIsa 客户端把每次调用的花费写到同一个文件，运行日志按起止时间算出这次花了多少。

## 接到例程上

**脚本型例程**（新词监控的预跑、交易雷达的扫描）：在原命令前面包一层 `wrap`，开始、结束、退出码、报错和花费都自动记：

```bash
python3 <仓库目录>/lib/runlog/runlog.py wrap 早间预跑 -- bash prescan.sh morning
```

**Agent 自己动手的例程**（社媒分析收链接、写播报、复盘）：开工记一行，收工记一行：

```bash
RID=$(python3 <仓库目录>/lib/runlog/runlog.py start 早报)
# ……干活……
python3 <仓库目录>/lib/runlog/runlog.py end "$RID" --status ok --outputs 12 --pushed
# 部分数据源失败：--status partial --sources "producthunt=ok,reddit=fail:429"
```

**每晚体检**（完整档）：总结之前跑一次，没问题只输出一行，省额度：

```bash
python3 <仓库目录>/lib/runlog/runlog.py check --days 1 --expect 早报,午报,晚报
```

会报出：失败和部分失败的运行、超过 2 小时没有结束记录的运行、连续两次失败的例程、`--expect` 里今天该跑没跑的例程、花费比前 7 天同期平均高 50% 以上。

**每周归档**（完整档）：`python3 <仓库目录>/lib/runlog/runlog.py prune --keep-days 90`

**审批和规则变更**（每档都有）：

```bash
python3 <仓库目录>/lib/runlog/runlog.py approve --kind spend --ask "查 300 个域名的外链，约 3 美元" --answer "同意"
python3 <仓库目录>/lib/runlog/runlog.py rule --where 新词播报 --what "老站不推" --why "11-08 推了一个 3 年前的站" --before "<改之前的原文>"
```

## 加进岗位说明的一段

开了哪一档，就把对应的句子加进 Bot 的长期指令（`<仓库目录>` 换成真实路径，不需要的档位那几句删掉）：

```text
运行日志（RUNLOG_HOME 和 AISA_CALL_LOG 已经设好）：
- 每次请我批准花钱、对外发送、删除，等我回复后用 runlog.py approve 记下请求和我的回复。
- 每次按我的纠正改技能、例程或长期指令，用 runlog.py rule 记下改了什么、为什么、改之前的原文。
- 【标准档起】脚本型例程用 runlog.py wrap 包住原命令；你自己动手的例程开工 runlog.py start、收工 runlog.py end，如实写状态、产出条数、有没有推送，失败或部分失败要写原因。
- 【完整档】每晚总结前先跑 runlog.py check --days 1 --expect <今天该跑的例程>，输出不是「运行正常」就把每一条放进总结最前面。每周日跑一次 runlog.py prune。
- 日志里不写 Key、密码、Cookie、Token。日志和账本一样，只追加不改写。
```

## 没法跑脚本的 Agent

有的 Agent 不能执行命令，也可以让它自己按同样的字段手写 `runs.jsonl`。但这样每次都要它自己拼 JSON、算时间，**比跑脚本更费额度**，也更容易漏记，能跑脚本就跑脚本。

## 验收

1. `wrap` 一条必定成功的命令和一条必定失败的命令，`runs.jsonl` 各有开始和结束两行，失败那行有退出码和报错。
2. `start` 之后不 `end`，跑 `check --stuck-h 0`，能看到「卡住」。
3. 记一条审批、一条规则变更，确认文件里有，且没有出现任何 Key。
4. 开了完整档的，看一次每晚总结，确认体检结果在最前面。
