# AGENTS.md：给 Agent 的安装说明

你是一个 Agent（Grok Bot、Muse、Dot、Hermes、OpenClaw、Claude Code、Codex 都可以），用户让你「按这个仓库把自己装成某个 Bot」。照下面做，**一步一步来，每步做完再进下一步**。

## 0. 先确认这几件事（一次只问一个问题）

1. **要装哪个 Bot**：
   - `newterm` 新词监控：每天三次播报新出现、可被搜索的词，给出海工具站找需求
   - `site-ops` 出海站点运营：按词找站、查竞品指标、提交免费导航站
   - `social-kb` 社媒分析：发链接给你，你取原文、整理、提取、存知识库。可选抖音评论区模块
   - 附带：`trade-radar` 交易雷达：盯价格异动和突发事件，分析后推送，交易由用户决定（目录在 `extras/trade-radar/`）
2. **工作目录**：默认 `/workspace/<bot 名>`。
3. **推送方式**：在当前聊天里回复就行，还是有别的渠道。
4. **要不要开运行日志**（可选，默认不开）：先告诉用户「开了会多消耗你的 Bot 额度」，再给三档让他选：轻量（只记审批和规则变更，几乎不耗额度）/ 标准（再加每次例程的运行记录）/ 完整（再加每晚体检、每周归档）/ 不开。说明见 `lib/runlog/README.md`。

一个 Bot 只装一个岗位。用户想要多个，建议分别建多个 Bot，岗位说明更清楚，也不会互相干扰。

## 1. 拿到代码

```bash
git clone https://github.com/Pluviobyte/saas-growth-agents.git <仓库目录>
python3 <仓库目录>/tests/test_dry_run.py      # 不需要 Key，全部 OK 才继续
```

只依赖 Python 3.10+ 标准库。`newterm` 额外需要 `bots/newterm/requirements.txt`，用它的 `install.sh` 安装。

## 2. Key：只放保险库，不进聊天、不进文件、不进记忆

- 需要的 Key：`AISA_API_KEY`（必填，在 https://go.aisa.one/rain 注册后，到控制台创建）。其他可选 Key 见各 Bot 的 `job.md`。
- **请用户自己把 Key 放进你的保险库 / Secret 存储**。如果你没有保险库，请用户写进工作目录下权限为 600 的 `.env`。
- 用户把 Key 直接贴进聊天时：照常使用，但提醒用户这样不安全、建议之后换一个新 Key；**不要把 Key 写进记忆、技能、笔记或任何回复里**。
- 验证 Key（免费，不扣钱）：`python3 <仓库目录>/lib/aisa/aisa_cli.py balance`

## 3. 先手动跑一次

打开 `bots/<bot>/job.md`（交易雷达是 `extras/trade-radar/job.md`），把里面的岗位说明中的 `<仓库目录>`、`<工作目录>` 换成真实路径，然后按它**手动做一遍**：

- `social-kb`：让用户发一条链接，你完整走一遍
- `trade-radar`：复制 `config.example.json` 为 `<工作目录>/config.json`，跑一次 `scan.py`
- `newterm`：`bash bots/newterm/install.sh <工作目录>`，再跑一次 `prescan.sh morning`
- `site-ops`：让用户给一个词，跑一次 `serp_sites.py`

把结果给用户看，问「这样可以吗，哪里要改」。**改到用户满意为止。**

## 4. 存成技能、设成例程

用户确认之后：

1. 把（改好的）岗位说明存成你的技能或长期指令。`newterm` 还要存 `bots/newterm/skills/` 下的两个技能；`site-ops` 存 `bots/site-ops/skills/directory-submit`；`social-kb` 的抖音评论区模块存 `bots/social-kb/douyin-comments`。
2. 按同一目录下的 `routines.md` 建例程。时间都是 Asia/Shanghai，用户在别的时区就先问。
3. 用户开了运行日志的：按 `lib/runlog/README.md` 设好 `RUNLOG_HOME` 和 `AISA_CALL_LOG`，把对应档位的那段话加进长期指令，脚本型例程的命令前面包上 `runlog.py wrap`。没开的跳过这一步，也不要自己顺手加上。
4. 只记这些到记忆：用户的称呼、时区、启用了哪些数据源、工作目录、运行日志开了哪一档。**不记 Key。**

## 5. 验收

按同一目录下的 `check.md` 逐条过一遍，把结果告诉用户。没过的项要说清楚卡在哪。开了运行日志的，再过一遍 `lib/runlog/README.md` 末尾的验收。

## 不管装哪个 Bot，都守这三条

1. 状态写进文件和账本，每次开工先读账本，不靠记忆。
2. 缺工具、拿不到数据、接口报错，必须说，不能跳过或编造。
3. 花钱、对外发送、删除、下单，必须用户点头。`trade-radar` 永远不下单。

## 费用

所有数据都走 AIsa，按次计费。每次请求都带最高价（默认 0.02 美元，部分接口单独放宽到 0.05 到 0.06 美元），超价的请求会被直接拒绝。
不确定一个调用多少钱时，先加 `--quote` 问价：`aisa_cli.py run --quote <函数> ...`。
