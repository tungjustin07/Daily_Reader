"""
Daily Digest — fetch, summarize, email.

Config lives in config.yaml. This file rarely needs editing.

Usage:
    python digest.py             # full run + send email
    python digest.py --dry-run   # print to terminal, no email
"""

import argparse
import hashlib
import logging
import os
import re
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import httpx
import yaml
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# LOAD CONFIG
# ─────────────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "config.yaml"

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler("logs/digest.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("digest")

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "digest.db"

def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            url_hash TEXT PRIMARY KEY,
            url      TEXT,
            seen_at  TEXT
        )
    """)
    conn.commit()
    return conn

def is_seen(conn, url: str) -> bool:
    h = hashlib.sha256(url.encode()).hexdigest()
    return conn.execute("SELECT 1 FROM seen WHERE url_hash=?", (h,)).fetchone() is not None

def mark_seen(conn, url: str):
    h = hashlib.sha256(url.encode()).hexdigest()
    conn.execute(
        "INSERT OR IGNORE INTO seen (url_hash, url, seen_at) VALUES (?,?,?)",
        (h, url, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()

# ─────────────────────────────────────────────────────────────────────────────
# FETCH
# ─────────────────────────────────────────────────────────────────────────────

def fetch_full_text(url: str) -> str:
    try:
        resp = httpx.get(f"https://r.jina.ai/{url}", timeout=20, follow_redirects=True)
        if resp.status_code == 200 and len(resp.text) > 300:
            return resp.text[:12000]
    except Exception as e:
        log.warning(f"Jina fetch failed for {url}: {e}")
    return ""

def fetch_rss_items(source: dict, cutoff: datetime, conn, max_items: int) -> list[dict]:
    log.info(f"Fetching: {source['name']}")
    feed = feedparser.parse(source["url"])
    items = []
    for entry in feed.entries[:max_items * 3]:
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub:
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
        if is_seen(conn, entry.link):
            continue
        body = fetch_full_text(entry.link) or entry.get("summary", "")
        if not body:
            continue
        items.append({
            "source": source["name"],
            "title":  entry.get("title", "Untitled"),
            "url":    entry.link,
            "body":   body,
            "type":   "article",
        })
        if len(items) >= max_items:
            break
    return items

def fetch_podcast_items(source: dict, cutoff: datetime, conn, max_items: int, whisper_model: str) -> list[dict]:
    log.info(f"Fetching podcast: {source['name']}")
    feed = feedparser.parse(source["url"])
    items = []
    for entry in feed.entries[:max_items]:
        pub = entry.get("published_parsed") or entry.get("updated_parsed")
        if pub:
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue
        audio_url = next(
            (e.href for e in entry.get("enclosures", []) if "audio" in e.get("type", "")),
            None
        )
        if not audio_url or is_seen(conn, entry.link):
            continue
        transcript = transcribe_audio(audio_url, entry.get("title", ""), whisper_model)
        if not transcript:
            continue
        items.append({
            "source": source["name"],
            "title":  entry.get("title", "Untitled"),
            "url":    entry.link,
            "body":   transcript,
            "type":   "podcast",
        })
    return items

def transcribe_audio(audio_url: str, title: str, whisper_model: str) -> str:
    try:
        import whisper
    except ImportError:
        log.error("whisper not installed — skipping podcast")
        return ""
    log.info(f"Transcribing: {title}")
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        with httpx.stream("GET", audio_url, timeout=120, follow_redirects=True) as r:
            with open(tmp_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        model = whisper.load_model(whisper_model)
        result = model.transcribe(tmp_path, fp16=False)
        return result["text"][:12000]
    except Exception as e:
        log.error(f"Transcription failed for {title}: {e}")
        return ""
    finally:
        Path(tmp_path).unlink(missing_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARIZE
# ─────────────────────────────────────────────────────────────────────────────

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def build_prompts(persona: str) -> tuple[str, str, str]:
    article_prompt = f"""Summarize the following article for {persona}.

Format:
**TL;DR** (1 sentence)
**Key points** (3 bullets, max 15 words each)
**Why it matters** (1 sentence relevance to revenue operations or AI)

Under 120 words. Be direct, skip filler phrases.

Article: {{body}}"""

    podcast_prompt = f"""Summarize this podcast transcript for {persona}.

Format:
**Episode summary** (2 sentences)
**Top 3 takeaways** (bullets, max 15 words each)
**Best quote** (most insightful line verbatim)

Under 150 words.

Transcript: {{body}}"""

    rollup_prompt = f"""You are {persona}. Given today's article summaries, write a 3-sentence big-picture paragraph connecting the themes. What's the signal across all of these?

Summaries:
{{summaries}}"""

    return article_prompt, podcast_prompt, rollup_prompt


def summarize(item: dict, article_prompt: str, podcast_prompt: str, model: str) -> str | None:
    template = podcast_prompt if item["type"] == "podcast" else article_prompt
    try:
        msg = client.messages.create(
            model=model,
            max_tokens=400,
            messages=[{"role": "user", "content": template.format(body=item["body"][:10000])}]
        )
        return msg.content[0].text
    except Exception as e:
        log.error(f"Summarization failed for {item['title']}: {e}")
        return None

def generate_rollup(summaries: list[str], rollup_prompt: str, model: str) -> str:
    if len(summaries) < 2:
        return ""
    try:
        combined = "\n\n---\n\n".join(summaries[:10])
        msg = client.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": rollup_prompt.format(summaries=combined)}]
        )
        return msg.content[0].text
    except Exception as e:
        log.error(f"Rollup failed: {e}")
        return ""

# ─────────────────────────────────────────────────────────────────────────────
# RENDER EMAIL
# ─────────────────────────────────────────────────────────────────────────────

def render_html(items: list[dict], rollup: str) -> str:
    today = datetime.now().strftime("%A, %B %-d")
    sections = ""
    for item in items:
        icon = "🎙" if item["type"] == "podcast" else "📄"
        summary_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item["summary"])
        summary_html = summary_html.replace("\n", "<br>")
        sections += f"""
        <div style="margin-bottom:28px;padding-bottom:24px;border-bottom:1px solid #e8e8e8">
          <p style="margin:0 0 4px;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.08em">{icon} {item['source']}</p>
          <h2 style="margin:0 0 10px;font-size:18px;font-weight:600;color:#1a1a1a;line-height:1.3">
            <a href="{item['url']}" style="color:#1a1a1a;text-decoration:none">{item['title']}</a>
          </h2>
          <div style="font-size:14px;line-height:1.7;color:#333">{summary_html}</div>
          <p style="margin:10px 0 0"><a href="{item['url']}" style="font-size:12px;color:#4f6ef7">Read full →</a></p>
        </div>"""

    rollup_section = ""
    if rollup:
        rollup_section = f"""
        <div style="background:#f5f7ff;border-left:3px solid #4f6ef7;padding:16px 20px;margin-bottom:28px;border-radius:0 8px 8px 0">
          <p style="margin:0 0 6px;font-size:11px;font-weight:600;color:#4f6ef7;text-transform:uppercase;letter-spacing:.08em">🧠 Big picture</p>
          <p style="margin:0;font-size:14px;line-height:1.7;color:#333">{rollup}</p>
        </div>"""

    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f4f4f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
    <div style="max-width:600px;margin:32px auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
      <div style="background:#1a1a1a;padding:28px 32px">
        <p style="margin:0;font-size:11px;color:#888;text-transform:uppercase;letter-spacing:.1em">Daily Digest</p>
        <h1 style="margin:4px 0 0;font-size:24px;font-weight:700;color:#fff">{today}</h1>
        <p style="margin:6px 0 0;font-size:13px;color:#aaa">{len(items)} items · AI-summarized</p>
      </div>
      <div style="padding:32px">{rollup_section}{sections}
        <p style="margin:0;font-size:11px;color:#bbb;text-align:center">Your daily digest</p>
      </div>
    </div></body></html>"""

def render_text(items: list[dict], rollup: str) -> str:
    today = datetime.now().strftime("%A, %B %-d")
    lines = [f"DAILY DIGEST — {today}", "=" * 50, ""]
    if rollup:
        lines += ["BIG PICTURE", rollup, "", "-" * 50, ""]
    for item in items:
        lines += [item["source"].upper(), item["title"], item["url"], "", item["summary"], "", "-" * 50, ""]
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# SEND EMAIL
# ─────────────────────────────────────────────────────────────────────────────

def send_email(subject: str, html: str, text: str):
    key = os.getenv("RESEND_API_KEY")
    if not key:
        log.warning("RESEND_API_KEY not set — skipping email")
        return
    try:
        import resend
        resend.api_key = key
        resend.Emails.send({
            "from":    os.getenv("EMAIL_FROM"),
            "to":      [os.getenv("EMAIL_TO")],
            "subject": subject,
            "html":    html,
            "text":    text,
        })
        log.info(f"Email sent to {os.getenv('EMAIL_TO')}")
    except Exception as e:
        log.error(f"Email failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run(dry_run=False):
    cfg = load_config()
    s = cfg["settings"]
    sources = cfg["sources"]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=s["lookback_hours"])
    conn = init_db()
    article_prompt, podcast_prompt, rollup_prompt = build_prompts(s["persona"])

    # 1. Fetch
    raw_items = []
    for source in sources:
        try:
            if source["type"] == "podcast":
                raw_items += fetch_podcast_items(source, cutoff, conn, s["max_items_per_source"], s["whisper_model"])
            else:
                raw_items += fetch_rss_items(source, cutoff, conn, s["max_items_per_source"])
        except Exception as e:
            log.error(f"Source '{source['name']}' failed: {e}")

    log.info(f"Fetched {len(raw_items)} new items")
    if not raw_items:
        log.info("Nothing new — skipping email")
        return

    # 2. Summarize
    results, summaries_only = [], []
    for item in raw_items:
        summary = summarize(item, article_prompt, podcast_prompt, s["model"])
        if summary:
            item["summary"] = summary
            results.append(item)
            summaries_only.append(summary)
            mark_seen(conn, item["url"])

    # 3. Rollup
    rollup = generate_rollup(summaries_only, rollup_prompt, s["model"])

    # 4. Render + send
    today = datetime.now().strftime("%a %b %-d")
    subject = f"Your digest — {today} ({len(results)} items)"
    html = render_html(results, rollup)
    text = render_text(results, rollup)

    if dry_run:
        print(text)
        return

    send_email(subject, html, text)

    # 5. Save local copy
    out = Path("logs") / f"digest-{datetime.now().strftime('%Y%m%d')}.txt"
    out.write_text(text)
    log.info(f"Saved to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
