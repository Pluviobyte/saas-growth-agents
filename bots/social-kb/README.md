# Social analysis pack

**English** · [简体中文](README.zh-CN.md)

**See something good? Drop the link and your agent files it into your knowledge base.** X, Douyin, RedNote, YouTube, WeChat articles or any web page: one link brings back the original. For Douyin it can also pull the full comment section.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../../assets/social-flow-dark.svg">
  <img alt="Data flow: your links are fetched through AIsa, while Douyin comments are pulled in your own browser. Scripts dedupe, normalize and build the comment report. The agent summarizes, compares with your workflow, files the note into the knowledge base and pushes a summary with suggestions to you. Skills only change with your OK." src="../../assets/social-flow-light.svg" width="900">
</picture>

Install it like the other bots by sending this to your agent:

```text
Read AGENTS.md in https://github.com/Pluviobyte/saas-growth-agents and set yourself up as the social-kb (social analysis) bot. Ask me one question at a time.
```

## What it does

You send a link and it runs the same steps every time:

1. **Dedupe**: if the link was saved before, it tells you so. It recognizes the same tweet even with different share parameters.
2. **Fetch the original**: each platform goes through its own API. If it can't get the content, it says so instead of inventing a summary from the title.
3. **Summarize**: one-line summary, key points, actionable steps, tools and links mentioned, author and source link.
4. **Compare with your workflow**: what you already do, what you don't do yet but should (and exactly how to plug it in), and what doesn't apply to you.
5. **File it**: saved by topic in `kb/<topic>.md`, merged with notes on the same topic.
6. **Reply**: a one-line summary plus anything worth doing. Every Sunday it also sends a weekly digest with the three things most worth trying.

Say "check the comments" on a Douyin video and it pulls the whole comment section, groups it into doubts, questions, comparisons and user experience, and adds that to the note.

The job description is in [job.md](job.md), the routines in [routines.md](routines.md), and the acceptance checklist in [check.md](check.md). These docs are in Chinese; agents read them fine.

## Which API each platform uses

| Link | Source | What you get |
|---|---|---|
| x.com / twitter.com | AIsa · Twitter | tweet text, author, engagement |
| douyin.com / v.douyin.com | AIsa · TikHub Douyin | title and description, author, stats, video URL |
| xiaohongshu.com / xhslink.com | AIsa · TikHub RedNote | title, body, author, stats |
| youtube.com / youtu.be | AIsa · DataForSEO YouTube | video info, full transcript |
| WeChat articles and other pages | AIsa · Firecrawl, falling back to Tavily | Markdown body |
| Douyin comments | your own browser (no AIsa) | top-level comments and every reply |

[AIsa](https://go.aisa.one/rain) is one key for thousands of APIs, pay per call. Every request carries a price cap and anything over it is rejected. Add `--quote` to check a price first; quotes are free.

> The AIsa link is the author's referral link.

## Douyin comments (formerly douyin-comments)

**An agent skill that pulls the complete comment section of a single Douyin video**: top-level comments, every nested reply and the video details, optionally the 720p video too. It outputs a `评论全文.md` report sorted by likes, plus the raw JSON.

Requests are sent from your own logged-in Chrome tab and signed by the page's own SDK. No paid APIs like TikHub, no Playwright, no reverse-engineering of a_bogus.

### Tested

| Video | Captured | Comment count shown | Requests / time | CAPTCHA |
| --- | --- | --- | --- | --- |
| 7-minute AI tool video | 83 top-level + 112 replies = 195 | 195 | 35 / 138 s | none |
| 46-minute tutorial | 77 top-level + 58 replies = 135 | 135 | 63 / 252 s | none |

The first result was checked line by line against clicking every "show replies" by hand, and matched exactly. Doing it by hand took about 6 minutes.

### How it works

Douyin's web comment API needs risk-control parameters such as a_bogus, msToken and uifid. Calling the reply endpoint with only `device_platform` and `aid` immediately triggers a click-the-characters CAPTCHA and the request hangs, because it's missing the 30-odd common parameters every normal page request carries.

So the skill doesn't build parameters itself. It **replays the page's own real request**:

1. `page_hook.js`: intercepts the first comment request the page sends and keeps its URL and headers as a template.
2. `page_fetch.js` (main path): every later request only swaps `aweme_id`, `cursor` and `comment_id` and copies the rest. Requests go out as XHR from inside the page, and the page's SDK adds the signature.
3. `page_ui_expand.js` (fallback): clicks each "show N replies" in the comment section so the page sends the requests itself, and only captures the responses. Slower, but it never trips risk control.
4. `recv.py`: a local receiver; the page POSTs each response page to `127.0.0.1`, where it's saved to disk.
5. `build_report.py`: merges and dedupes, checks every thread's reply count is complete, then writes `评论全文.md`.

Requests are spaced 2–4 seconds apart, with an extra 8–15 second pause every 15 requests.

### Install just this skill (Claude Code)

You need Claude Code connected to the Claude in Chrome extension (run `/chrome` in Claude Code), Chrome logged in to Douyin, Python 3 and curl.

```sh
git clone https://github.com/Pluviobyte/saas-growth-agents.git ~/saas-growth-agents
ln -s ~/saas-growth-agents/bots/social-kb/douyin-comments ~/.claude/skills/douyin-comments
```

If `~/.claude/skills/douyin-comments` already exists, check what's in it before replacing it. Then give Claude Code a Douyin video link and ask for the comments:

```text
Pull the comment section of this video: https://www.douyin.com/video/7xxxxxxxxxxxxxxxxxx
```

Three link types work: `douyin.com/video/<id>`, a profile link with `modal_id=<id>`, and `v.douyin.com` short links. Output goes to `.internal/抖音评论/<aweme_id>/` in the current project:

```
raw/                  # template, raw response pages, receiver log
comments_top.json     # top-level comments (deduped)
comments_replies.json # replies (deduped)
评论全文.md            # sorted by likes, replies indented under their comment
参考视频.mp4           # optional video
```

To use it in Grok Bot or other agents, see "在其他 Agent 里用" (using it in other agents) at the end of [SKILL.md](douyin-comments/SKILL.md).

### Installed douyin-comments before?

The old install was `git clone .../douyin-comments.git ~/.claude/skills/douyin-comments`, with the skill at the repo root. The skill now lives in a subfolder, so after `git pull` that folder is no longer a skill. Reinstall using the steps above: move the old folder out of the way, clone, and create the symlink. The old `Pluviobyte/douyin-comments` URL redirects here.

### Limits of the comments module

- **It never solves CAPTCHAs.** If one appears, the skill stops; you solve it in Chrome yourself, then it continues.
- Single videos only. It doesn't bulk-collect a creator's videos, and doesn't handle RedNote or Bilibili comments.
- Deleted, folded or author-only comments aren't returned by the API, so the total can be slightly below the count shown on the video.
- Videos with over a thousand comments: after about 500 top-level comments the API starts returning duplicates and folded comments can't be fetched. One test got 823 of 1067.
- Not yet tested: paging when a single thread has more than 20 replies; running inside Grok Bot and other agents.
