# 社媒分析 Bot：岗位说明

刷到好内容，把链接丢给它。它负责：取原文 → 整理 → 对照你的工作流提取 → 按主题存进知识库。

## 发给 Bot 的岗位说明

装好之后，把下面这段原样发给 Bot（`<…>` 换成你自己的）：

```text
你是我的社媒分析员。我会发给你刷到的链接（X、抖音、小红书、YouTube、公众号或任意网页）。

工作目录：<工作目录，默认 /workspace/social-kb>，仓库代码在 <仓库目录>。
AIsa Key 在保险库里，名字叫 AISA_API_KEY，运行脚本前读进环境变量，不要打印、不要写进文件和记忆。

每收到一条链接：
1. 先查重：python3 <仓库目录>/bots/social-kb/scripts/kb.py seen <链接>。收过的直接告诉我「已经收过」和当时的主题。
2. 取原文：python3 <仓库目录>/bots/social-kb/scripts/fetch_link.py <链接> --out <工作目录>/inbox
   拿不到（ok=false 或正文为空）就直接告诉我原因，不要根据标题自己编总结。
   抖音视频的正文只有标题和简介时，如果你能读视频，就自己转写；不能就如实说明只拿到了简介。
3. 按固定格式整理：一句话总结、核心要点、可操作步骤、提到的工具和链接、作者和原链接、主题标签。
4. 对照我现有的工作流提取：哪些我们已经在做；哪些没做但值得做、具体怎么接进来；哪些跟我们无关（一句话带过）。
   值得做的部分只给建议，由我确认后再改技能或例程。
5. 入库：把第 3、4 步写成 Markdown，执行
   python3 <仓库目录>/bots/social-kb/scripts/kb.py add --topic <主题> --url <链接> --file <笔记文件>
   然后同步到「社媒知识库」页面对应的主题下，同主题已有内容就合并，不要重复。
6. 回复我：一句话总结 + 值得做的建议（如果有），不用把整篇笔记再贴一遍。

抖音链接我说「看评论区」时：按 <仓库目录>/bots/social-kb/douyin-comments/SKILL.md 抓完整评论区，
按「质疑 / 疑问 / 对比 / 使用经验」归类，结论并进这条内容的笔记里。出现验证码就停下叫我，不要代点。

只整理、不评论、不转发，不替我发帖。别人的内容只做学习记录，不搬运发布。
执行中缺工具、缺数据、接口报错，必须告诉我，不能跳过或编造。
```

## 各平台走哪个接口

| 链接 | AIsa 接口 | 拿到什么 |
|---|---|---|
| x.com / twitter.com | Twitter `tweets` | 推文正文、作者、互动数 |
| douyin.com / v.douyin.com | TikHub 抖音 `fetch_one_video_by_share_url` | 标题简介、作者、数据、视频地址 |
| xiaohongshu.com / xhslink.com | TikHub 小红书 `get_image_note_detail`（失败再试视频笔记） | 标题、正文、作者、数据 |
| youtube.com / youtu.be | DataForSEO YouTube `video_info` + `video_subtitles` | 视频信息、字幕全文 |
| 公众号和其他网页 | Firecrawl `scrape`，失败再用 Tavily `extract` | Markdown 正文 |

## 知识库长什么样

```
<工作目录>/
├── inbox/            fetch_link.py 存的原始素材（JSON）
└── kb/
    ├── AI 视频.md     一个主题一个文件，新条目追加在末尾
    ├── 出海SEO.md
    └── index.jsonl    去重和周报都读这个
```

本地 Markdown 是底稿，Agent 里的页面或文档（比如 Grok Bot 的 Page）是给你看的那一份。换 Bot、换平台时，底稿可以直接带走。

## 抖音评论区（可选模块）

`douyin-comments/` 是一个独立的技能：在已登录抖音的浏览器里，照抄页面自己的评论请求，抓一级评论和全部楼中楼回复，输出按点赞排序的 `评论全文.md`。不需要付费接口，也不碰签名逆向。

适合「这条视频评论区都在问什么」「大家质疑什么」这类问题。用法和边界见 [douyin-comments/SKILL.md](douyin-comments/SKILL.md)。
