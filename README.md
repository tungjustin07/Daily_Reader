# Daily Reader

A personal AI digest that runs every Monday morning and emails a summary of RSS feeds, podcasts, and Twitter — all in one email.

## What it does

Runs every Monday at 7am PT via GitHub Actions:

1. **RSS / blogs** — fetches new articles from configured sources, pulls full text via Jina, summarizes each with Claude
2. **Podcasts** — downloads new episodes, transcribes with Whisper, summarizes
3. **Twitter people** — searches recent tweets from a curated list of ~90 thinkers, founders, and SV influencers; groups by theme (AI, Economics, Ideas, etc.)
4. **Trending hashtags** — finds the top 10 most engaged tweets from the past 7 days across `#RevOps #GTM #SaaS #B2BGrowth #AIforBusiness` and related tags
5. **Big picture rollup** — one paragraph connecting themes across all content
6. Sends a single HTML email via Resend

## Email layout

```
🧠 Big picture rollup
🐦 This Week on Twitter  (curated people, by theme)
🔥 Trending in RevOps / GTM / SaaS  (top hashtag tweets)
📄 RSS articles + 🎙 Podcast summaries
```

## Setup

### 1. Clone and configure sources

Edit `config.yaml` to add/remove RSS feeds and podcasts. No code changes needed — just edit the YAML and push.

```yaml
settings:
  lookback_hours: 168
  max_items_per_source: 3
  model: claude-haiku-4-5-20251001
  persona: "a senior RevOps and GTM consultant..."
  twitter_lookback_days: 7

sources:
  - name: Lenny's Newsletter
    type: rss
    url: https://www.lennysnewsletter.com/feed

  - name: All-In
    type: podcast
    url: https://allinchamathjason.libsyn.com/rss
```

To add a new source, copy any block, update `name`/`url`, commit and push.

**Finding RSS feeds:**
- Substack → `https://<name>.substack.com/feed`
- Ghost → `https://<site>/rss/`
- WordPress → `https://<site>/feed/`

### 2. Edit the Twitter people list

`twitter_people.py` contains two lists:
- `COLLISON_LIST` — Patrick Collison's curated thinkers/researchers
- `SV_INFLUENCERS` — high-engagement SV founders, AI leaders, GTM practitioners

Edit either list to add/remove handles. Also edit `HASHTAGS` to change which tags are monitored for trending content.

### 3. GitHub Secrets

Add these four secrets to your repo (Settings → Secrets → Actions):

| Secret | Description |
|--------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key (needs web_search tool access) |
| `RESEND_API_KEY` | Resend API key for email delivery |
| `EMAIL_FROM` | Sender address (must be a verified Resend domain) |
| `EMAIL_TO` | Your email address |

### 4. Enable the workflow

The workflow runs automatically every Monday at 7am PT. You can also trigger it manually from the Actions tab.

## Local development

```bash
# Install deps
pip install -r requirements.txt

# Create .env with your keys
cp .env.example .env   # then fill in values

# Test without sending email
python digest.py --dry-run

# Full run (sends email)
python digest.py
```

## Stack

- **Claude Haiku** — article summarization, Twitter search + theming, hashtag trending
- **Whisper** — podcast transcription (runs in GitHub Actions with ffmpeg)
- **Jina** — full-text article extraction from URLs
- **Resend** — transactional email delivery
- **GitHub Actions** — weekly cron scheduling, SQLite deduplication committed back to repo

## Deduplication

Already-seen article URLs are stored in `digest.db` (SQLite). The workflow commits this file back to the repo after each run so deduplication persists across runs.
