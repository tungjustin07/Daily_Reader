# Daily Reader

A daily email digest that fetches RSS feeds and podcast transcripts, summarizes them with Claude, and emails you a clean briefing every morning.

## What it does

- Fetches new articles from RSS/Substack sources published in the last 24 hours
- Downloads and transcribes podcast episodes via Whisper
- Summarizes each item with Claude Haiku (TL;DR + key points + why it matters)
- Generates a "Big Picture" rollup connecting themes across all items
- Sends a formatted HTML email via Resend
- Tracks seen URLs in a local SQLite DB to avoid duplicates

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
brew install ffmpeg  # required for podcast transcription
```

**2. Create `.env`**
```
ANTHROPIC_API_KEY=...
RESEND_API_KEY=...
EMAIL_FROM=digest@yourdomain.com
EMAIL_TO=you@gmail.com
```

**3. Edit `config.yaml`** to add your sources and set your persona.

**4. Run**
```bash
python digest.py --dry-run   # print to terminal, no email
python digest.py             # full run + send email
```

## Adding sources

In `config.yaml`, add an entry under `sources`:

```yaml
- name: My Newsletter
  type: rss          # or: podcast
  url: https://example.substack.com/feed
  tags: [gtm, ai]
```

Common RSS URL patterns:
- Substack: `https://<name>.substack.com/feed`
- Ghost: `https://<site>/rss/`
- WordPress: `https://<site>/feed/`

Commit and push — the next scheduled run picks it up automatically.

## Configuration

All settings live in `config.yaml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `lookback_hours` | 24 | How far back to fetch items |
| `max_items_per_source` | 3 | Cap per source to keep email manageable |
| `model` | `claude-haiku-4-5-20251001` | Swap to `claude-sonnet-4-6` for better summaries |
| `whisper_model` | `base` | `tiny` / `base` / `small` — transcription quality vs speed |
| `persona` | RevOps consultant | Shapes summarization tone and relevance filter |

## GitHub Actions

The workflow runs daily at 7am PT (14:00 UTC). Trigger manually from the Actions tab anytime.

Required secrets: `ANTHROPIC_API_KEY`, `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TO`
