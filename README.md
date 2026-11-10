<div align="center">

<img src="assets/icon.png" width="112" alt="saas-growth-agents">

# saas-growth-agents

### Hand your SaaS growth chores to an agent that runs them every day.

**Spot new search terms, find who ranks for them, check competitor backlinks, submit to directories, and file good posts into a knowledge base.**<br>
These jobs repeat daily and follow fixed steps, which makes them perfect SOPs for an agent.<br>
Create a bot, send it one sentence, and it reads this repo, asks you a few questions, and sets itself up.

[![Stars](https://img.shields.io/github/stars/Pluviobyte/saas-growth-agents?style=flat&color=111111&cacheSeconds=3600)](https://github.com/Pluviobyte/saas-growth-agents/stargazers) [![License](https://img.shields.io/badge/license-MIT-111111)](LICENSE) [![Python](https://img.shields.io/badge/python_3-stdlib_only-111111?logo=python&logoColor=white)](lib/aisa/client.py) [![Data](https://img.shields.io/badge/data-AIsa-F26B1D)](https://go.aisa.one/rain)<br>
[![Grok Bot](https://img.shields.io/badge/Grok_Bot-recommended-000000?logo=x&logoColor=white)](https://grok.com/refer/bot?code=NASHTX8NMYH3) ![Muse](https://img.shields.io/badge/Muse-333333) ![Dot](https://img.shields.io/badge/Dot-333333) ![Hermes](https://img.shields.io/badge/Hermes-333333) ![OpenClaw](https://img.shields.io/badge/OpenClaw-333333) ![Claude Code](https://img.shields.io/badge/Claude_Code-D97757?logo=claude&logoColor=white) ![Codex](https://img.shields.io/badge/Codex-111111)

**[Quick start](#quick-start)** &nbsp;·&nbsp; **[The bots](#the-bots)** &nbsp;·&nbsp; **[One-line setup](bootstrap.md)** &nbsp;·&nbsp; **[AGENTS.md](AGENTS.md)** &nbsp;·&nbsp; **[Grok Bot free for 14 days](https://grok.com/refer/bot?code=NASHTX8NMYH3)** &nbsp;·&nbsp; **English** · [简体中文](README.zh-CN.md)

<br>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/flow-dark.svg">
  <img alt="Data flow: sources go through AIsa into three script pipelines (new-term radar, site ops, social analysis). Scripts only do deterministic work such as collecting, deduping and logging. The agent analyzes, verifies and reports, then pushes to you to decide. State lives in files and ledgers that are read before every run. Spending, sending and deleting all need your OK." src="assets/flow-light.svg" width="900">
</picture>

</div>

<br>

These are the SOPs and scripts the author runs for their own SaaS tools aimed at overseas markets. Any agent that can run terminal commands and keep long-lived instructions can use them.

> **Coming from douyin-comments?** This repo *is* the old douyin-comments, now merged into the full growth system. The Douyin comments skill is unchanged and lives in the social analysis pack at [`bots/social-kb/douyin-comments/`](bots/social-kb/douyin-comments/SKILL.md). See [how to reinstall](bots/social-kb/README.md#installed-douyin-comments-before).

**The whole system runs on three rules:**

1. **Scripts do the deterministic work**: collecting, deduping, scoring and logging. Results are reproducible and replayable, never a model's "feeling".
2. **The agent judges**: it reads what the scripts produce, then analyzes, extracts, verifies and reports. If data is missing it says so instead of making things up.
3. **You decide**: the agent only pushes conclusions. Spending money, sending anything out and deleting all need your OK. Every correction you make becomes a new rule in its skills.

## The bots

| Bot | What you do | What it does |
|---|---|---|
| [New-term radar](bots/newterm/job.md) | Nothing | Three reports a day on newly searchable terms: new AI products, models, memes, templates. Sources include Google Trends, competitor sitemaps, new directory listings, Product Hunt, GitHub Trending, Reddit and TikTok |
| [Site ops](bots/site-ops/job.md) | Give it keywords and your product | Finds every site competing for a keyword, checks their DR and backlinks, tracks your own site's metrics daily, submits to free directories by the rules, and logs everything |
| [Social analysis pack](bots/social-kb/README.md) | Drop a link when you see something good | Fetches the original (X, Douyin, RedNote, YouTube, WeChat, any web page) → summarizes → extracts "what could improve your SOPs" against your own workflow → files it by topic. For Douyin it can also pull the full comment section |

Plus an unrelated extra, [Trade radar](extras/trade-radar/job.md): watches price moves and breaking events and pushes an analysis. **It analyzes only and never places orders.**

## Which agent

**Grok Bot, Muse, Dot, Hermes and OpenClaw** all work, and so do Claude Code and Codex. [AGENTS.md](AGENTS.md) has the generic steps; each product just has its own name for "routines" (scheduled tasks) and "vault" (secret storage).

**The author recommends Grok Bot.** It comes with a cloud computer, a vault, skills and routines. These SOPs were first built on Grok Bot, and once installed they run around the clock on routines.

> No Grok Bot yet? Sign up with the author's invite link to get 14 days free: **https://grok.com/refer/bot?code=NASHTX8NMYH3**
> (This is a referral link and the author is rewarded for sign-ups. Grok's official page has the current terms.)

## Quick start

1. Create a new bot in your agent.
2. Send it the matching sentence from [bootstrap.md](bootstrap.md), for example:

   ```text
   Read AGENTS.md in https://github.com/Pluviobyte/saas-growth-agents and set yourself up as the newterm (new-term radar) bot. Ask me one question at a time.
   ```

3. It asks you to put your [AIsa](https://go.aisa.one/rain) key in its vault, does one run by hand to show you, and only turns it into a routine once you're happy.

The whole process is **do it once → tweak until it's right → save as a skill → schedule as a routine**.

The job descriptions and SOP docs inside the repo are written in Chinese. Agents read them fine, and the bot will talk to you in your language.

## Where the data comes from

All external data goes through [AIsa](https://go.aisa.one/rain): one key for thousands of APIs, pay per call, with MCP support. This repo uses:

- **SEO**: DataForSEO SERP and Google Trends, Ahrefs
- **Social**: Twitter, TikHub (Douyin, RedNote), DataForSEO YouTube (transcripts, video info)
- **Web**: Firecrawl, Tavily
- **Trade radar**: CoinGecko, Financial (US stocks), Polymarket, FRED, Perplexity

Each API maps to one function in [lib/aisa/sources.py](lib/aisa/sources.py), with paths and parameters checked against AIsa's official OpenAPI spec.
Every request carries a price cap and anything over it is rejected. Not sure what a call costs? Add `--quote` to ask first; quotes are free.

> The AIsa links are the author's referral links. The Douyin comments module doesn't use AIsa; it runs in your own logged-in browser for free.

## Optional: run logs

For a sturdier setup where you can trace what went wrong, add the [run log module](lib/runlog/README.md). It records:

- whether each routine ran, whether it succeeded, and what it cost
- what you approved
- when a rule was changed, and why

A nightly health check lists failed, stuck and missed runs, plus cost spikes.

> ⚠️ **It uses more of your bot's quota, so it's off by default and the bot asks during setup.** There are three levels:
> - Light: approvals and rule changes only, almost no extra quota.
> - Standard: adds a record for every routine run.
> - Full: adds the nightly check and weekly archiving.
>
> Logs are local files only, so AIsa costs don't change. (The module's doc is in Chinese; agents read it fine.)

## Repo layout

```
saas-growth-agents/
├── AGENTS.md               setup steps for the agent
├── bootstrap.md            the one sentence to send your bot
├── lib/aisa/               AIsa layer: client.py (stdlib), sources.py (data sources), aisa_cli.py (CLI)
├── lib/runlog/             optional: run log, approvals, rule changes, nightly health check (uses more bot quota)
├── bots/
│   ├── newterm/            new-term radar: job.md · routines.md · check.md · pipeline/ · skills/ · install.sh
│   ├── site-ops/           site ops: job.md · routines.md · check.md · scripts/ · skills/
│   └── social-kb/          social analysis pack: README.md · job.md · routines.md · check.md · scripts/ · douyin-comments/
├── extras/trade-radar/     trade radar (extra)
├── skills/agent-setup/     for Claude Code / Codex: asks what you need and writes a tailored setup message for your bot
├── templates/              ledger formats
└── tests/                  dry-run tests that need no key (all sample data is fictional)
```

Every bot folder has the same shape: `job.md` is the job description, `routines.md` the schedule, `check.md` the acceptance checklist.

## Try it without a key

```bash
git clone https://github.com/Pluviobyte/saas-growth-agents.git && cd saas-growth-agents
python3 tests/test_dry_run.py                                        # full dry run
AISA_DRY_RUN=1 python3 bots/site-ops/scripts/serp_sites.py "ai video generator"
```

## Boundaries

- **No CAPTCHA solving, no filling in passwords, no signing up for accounts on your behalf.** It stops and hands those to you.
- **Directory submissions only go to free sites that don't require a backlink.** Paid and link-exchange sites are skipped, with the reason logged.
- **Out of scope for this repo**:
  - browser-extension batch jobs: unclear license
  - scraping through shared accounts: against platform terms
  - mass blog-comment backlinks: that's link spam
  - real site pools, submission logs and keyword lists: personal data
- Other people's content is for learning notes only, never for reposting. Keep request rates low and follow each platform's terms.
- Trade radar contains no order-placing code, and its ledger rejects position and order fields. Its output is information, not investment advice.

## License

[MIT](LICENSE). Third-party services and credits are in [NOTICE.md](NOTICE.md).
