# 社媒分析包

[English](README.md) · **简体中文**

**刷到好内容，丢一个链接，Agent 帮你拆进知识库。** X、抖音、小红书、YouTube、公众号、任意网页，一个链接取回原文；抖音还能抓完整评论区。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../assets/social-flow-dark.zh-CN.svg">
  <img alt="数据流：你丢的链接经 AIsa 取原文，抖音评论区在你自己的浏览器里抓；脚本负责查重、统一格式、出评论全文；Agent 整理并对照你的工作流提取，写进知识库，再把一句话总结和建议推给你；你点头后才改技能。" src="../../assets/social-flow-light.zh-CN.svg" width="900">
</picture>

装法和其他 Bot 一样：把这句话发给你的 Agent。

```text
读 https://github.com/Pluviobyte/saas-growth-agents 的 AGENTS.md，按它把你自己装成 social-kb（社媒分析）Bot。一次只问我一个问题。
```

## 它做什么

你发一条链接，它按固定流程走完：

1. **查重**：收过的链接直接告诉你「已经收过」，同一条推文换了分享参数也认得出来。
2. **取原文**：按平台走对应接口，拿不到就如实说，不根据标题编总结。
3. **整理**：一句话总结、核心要点、可操作步骤、提到的工具和链接、作者和原链接。
4. **对照你的工作流提取**：哪些你已经在做；哪些没做但值得做、具体怎么接进来；哪些跟你无关。
5. **入库**：按主题存进 `kb/<主题>.md`，同主题合并。
6. **回复你**：一句话总结加值得做的建议。每周日再给一份周报，挑出最值得动手试的三条。

抖音视频说一句「看评论区」，它会抓完整评论区，按「质疑 / 疑问 / 对比 / 使用经验」归类，并进这条内容的笔记里。

岗位说明的原文在 [job.md](job.md)，例程在 [routines.md](routines.md)，装好后的验收清单在 [check.md](check.md)。

## 各平台走哪个接口

| 链接 | 接口 | 拿到什么 |
|---|---|---|
| x.com / twitter.com | AIsa · Twitter | 推文正文、作者、互动数 |
| douyin.com / v.douyin.com | AIsa · TikHub 抖音 | 标题简介、作者、数据、视频地址 |
| xiaohongshu.com / xhslink.com | AIsa · TikHub 小红书 | 标题、正文、作者、数据 |
| youtube.com / youtu.be | AIsa · DataForSEO YouTube | 视频信息、字幕全文 |
| 公众号和其他网页 | AIsa · Firecrawl，失败再用 Tavily | Markdown 正文 |
| 抖音评论区 | 你自己的浏览器（不走 AIsa） | 一级评论、全部楼中楼回复 |

[AIsa](https://go.aisa.one/rain) 是一个 Key 调几千个接口的数据平台，按次计费。每次请求都带最高价，超价直接拒绝；不确定价格就先加 `--quote` 问价，问价不花钱。

> AIsa 链接是作者的邀请链接。

## 抖音评论区（原 douyin-comments）

**抓取抖音单条视频完整评论区的 Agent Skill。** 抓取范围包括一级评论、全部楼中楼回复和视频详情，可选下载 720p 视频，最终输出一份按点赞排序的 `评论全文.md` 和原始 JSON。

请求在你自己已登录的 Chrome 页面里发出，签名交给页面自带的 SDK 计算。不需要 TikHub 之类的付费接口，不需要 Playwright，也不用逆向 a_bogus。

### 实测

| 视频 | 抓到 | 视频显示评论数 | 请求 / 耗时 | 验证码 |
| --- | --- | --- | --- | --- |
| 7 分钟 AI 工具视频 | 一级 83 + 回复 112 = 195 | 195 | 35 次 / 138 秒 | 无 |
| 46 分钟教程 | 一级 77 + 回复 58 = 135 | 135 | 63 次 / 252 秒 | 无 |

第一条与逐个手动点「展开回复」抓到的结果逐条比对，完全一致。手动方式用了约 6 分钟。

### 原理

抖音 Web 评论接口要带 a_bogus、msToken、uifid 等风控参数。如果只带 `device_platform` 和 `aid` 去调楼中楼接口，会立刻弹出文字点选验证码，请求一直挂起。原因是缺少页面正常请求里都有的那 30 多个公共参数。

所以这个 skill 不自己拼参数，而是**照抄页面的真实请求**：

1. `page_hook.js`：拦截页面自己发出的第一次评论请求，把它的 URL 和请求头记成模板。
2. `page_fetch.js`（主路线）：之后每次请求只替换 `aweme_id`、`cursor`、`comment_id` 三个参数，其余照抄。请求从页面内的 XHR 发出，由页面 SDK 补上签名。
3. `page_ui_expand.js`（兜底路线）：在评论区逐个点「展开 N 条回复」，由页面自己发请求，脚本只截获响应。这条路线慢，但不会触发风控。
4. `recv.py`：本机接收服务，页面把每一页响应 POST 到 `127.0.0.1` 落盘。
5. `build_report.py`：合并去重，逐楼核对回复数有没有抓全，再生成 `评论全文.md`。

请求节奏为每次间隔 2～4 秒，每 15 次额外停 8～15 秒。

### 单独装这个 skill（Claude Code）

需要 Claude Code 连接 Claude in Chrome 扩展（在 Claude Code 里执行 `/chrome`）、已登录抖音的 Chrome、Python 3 和 curl。

```sh
git clone https://github.com/Pluviobyte/saas-growth-agents.git ~/saas-growth-agents
ln -s ~/saas-growth-agents/bots/social-kb/douyin-comments ~/.claude/skills/douyin-comments
```

如果 `~/.claude/skills/douyin-comments` 已存在，先检查里面的内容，不要直接覆盖。然后在 Claude Code 里给一个抖音视频链接，并说明要抓评论：

```text
抓一下这条视频的评论区 https://www.douyin.com/video/7xxxxxxxxxxxxxxxxxx
```

支持三种链接：`douyin.com/video/<id>`、带 `modal_id=<id>` 的主页链接，以及 `v.douyin.com` 短链。产出默认写到当前项目的 `.internal/抖音评论/<aweme_id>/`：

```
raw/                  # 模板、每页原始响应、接收日志
comments_top.json     # 一级评论（去重）
comments_replies.json # 楼中楼回复（去重）
评论全文.md            # 按点赞排序，回复缩进在所属评论下面
参考视频.mp4           # 可选
```

在 Grok Bot 等其他 Agent 里用，看 [SKILL.md](douyin-comments/SKILL.md) 末尾的「在其他 Agent 里用」。

### 以前装过 douyin-comments

以前是 `git clone .../douyin-comments.git ~/.claude/skills/douyin-comments`，skill 在仓库根目录。现在 skill 挪到了子目录，`git pull` 之后那个目录就不再是一个 skill 了。按上面「单独装这个 skill」重新装一次即可：先把旧目录挪走，再 clone 并建符号链接。旧的仓库地址 `Pluviobyte/douyin-comments` 会自动跳转到这里。

### 评论区模块的边界

- **不代点验证码。** 出现验证码时 skill 会停下，由你在 Chrome 里手动完成，然后继续。
- 只处理单条视频，不批量采集博主的全部作品，也不支持小红书和 B 站的评论区。
- 被删除、被折叠或仅作者可见的评论，接口不会返回，所以抓到的总数可能略少于视频显示的评论数。
- 上千条评论的视频：一级评论翻到约 500 条之后接口开始返回重复内容，被折叠的评论也拿不到，实测抓到 823 / 1067。
- 尚未实测：单个楼超过 20 条回复时的翻页；在 Grok Bot 等其他 Agent 里运行。
