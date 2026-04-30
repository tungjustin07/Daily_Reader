# End-of-Day Log

---
## 2026-04-30

### 🏗️ What Was Built / Shipped
- **feat:** native Reddit fetcher (`fetch_reddit_items`) in `digest.py` — pulls Reddit's public JSON API directly instead of RSS, so we get score + num_comments and can rank by engagement.
- Self-posts use `selftext` directly (Jina is blocked by Reddit); link-posts still go through Jina against the linked article.
- Sets a real `User-Agent` header to avoid Reddit's 429s on default httpx UA.
- Sorts candidates by `score + num_comments` and takes the top `max_items_per_source` (3).
- API `limit` parameter scoped to `max(max_items, 3)` so we don't pull more than needed.
- `config.yaml`: r/gtmengineering and r/ClaudeCode switched from `type: rss` to `type: reddit`.

### 🧭 Decisions Made
- **No min_score / min_comments thresholds** — just take the top-ranked posts. Simpler, no per-subreddit tuning.
- Use Reddit's JSON endpoint (no auth needed) instead of PRAW — keeps deps light.
- Prepend `[score: N, comments: M]` to body so the summarizer has engagement context.
- Skip stickies and NSFW posts.

### 🚧 Blockers and Failures
- ✅ None. Push initially rejected (remote had a `[skip ci]` seen-urls commit); resolved with `git pull --rebase`.

### 🔮 Open Questions / Tomorrow
- Watch tomorrow's digest run — confirm Reddit posts now contain real selftext (not "Reddit blocked" string) and the Lovable-style low-engagement post no longer appears.
- If r/gtmengineering daily volume is sparse, consider widening `time` window to `week`.
- Carryover from 04-17: `twitter-digest/` standalone repo still not pushed to GitHub.

### 📈 Git Stats
- 📝 Commits today: 1 (feat) + 1 bot seen-urls commit
- 📁 Files changed: 3 (config.yaml, digest.py, digest.db)
- 🏷️ Feature areas: feat, chore

### 💾 Checkpoints Today
- None stored today for this project

---
## 2026-04-17

### 🏗️ What Was Built / Shipped
- **chore:** Switched `TWITTER_SEARCH_MODEL` from `claude-sonnet-4-6` → `claude-haiku-4-5-20251001` in [digest.py:255](digest.py:255) to cut daily digest cost. Summary model was already Haiku.

### 🧭 Decisions Made
- Accept potentially less reliable tool-use on Haiku in exchange for ~3× cheaper LLM tokens (~30% total run-cost reduction).
- Deferred dropping `TWITTER_MAX_SEARCHES` (6) and hashtag `max_uses` (5) for now — `web_search` at $10/1k is now the larger line item if further cuts are needed.

### 🚧 Blockers and Failures
✅ None

### 🔮 Open Questions / Tomorrow
- Monitor the next few digest runs for regressions — Haiku historically ignored the `web_search` tool; that was the original reason Sonnet was introduced.
- If quality drops, either revert to Sonnet or reduce `TWITTER_MAX_SEARCHES` and keep Haiku.

### 📈 Git Stats
- 📝 Commits today: 1
- 📁 Files changed: 1 (`digest.py`)
- 🏷️ Feature areas: chore

### 💾 Checkpoints Today
- None stored today for Daily_Reader
