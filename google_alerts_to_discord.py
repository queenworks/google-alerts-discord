#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests


FEEDS_FILE = Path("feeds.json")
STATE_FILE = Path("state/google_alerts_seen.json")

MAX_POSTS_PER_FEED = 21
MAX_SEEN_PER_FEED = 500
DISCORD_TIMEOUT_SECONDS = 20

# 初回は投稿せず、既読登録だけする
SKIP_FIRST_RUN = True

IMPORTANT_KEYWORDS = [
    # 気象・防災
    "台風", "線状降水帯", "記録的", "避難", "洪水", "氾濫", "土砂災害",
    "猛暑", "豪雨", "大雨", "暴風", "災害",
    "heatwave", "flood", "wildfire", "disaster", "extreme weather",

    # 投資・企業
    "決算", "急落", "急騰", "下方修正", "上方修正", "買収", "提携",
    "earnings", "guidance", "acquisition", "merger", "plunge", "surge",
]


def clean_text(text: str) -> str:
    """GoogleアラートRSS内の <b> や &nbsp; をきれいにする"""
    if not text:
        return ""

    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def trim(text: str, max_len: int) -> str:
    text = clean_text(text)
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def env_value(name: str) -> str:
    return os.environ.get(name, "").strip()


def make_entry_id(entry) -> str:
    raw = (
        getattr(entry, "id", "")
        or getattr(entry, "link", "")
        or f"{getattr(entry, 'title', '')}|{getattr(entry, 'published', '')}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_important(title: str, summary: str = "") -> bool:
    text = f"{title} {summary}".lower()
    return any(keyword.lower() in text for keyword in IMPORTANT_KEYWORDS)


# 修正後
def discord_embed_payload(feed_conf, entry):
    hub = feed_conf.get("hub", "Google Alerts")
    name = feed_conf.get("name", "Alert")
    base_color = int(feed_conf.get("color", 0x3498DB))

    title = trim(getattr(entry, "title", "No title"), 250)
    link = getattr(entry, "link", "")
    summary = trim(getattr(entry, "summary", ""), 500)
    published = clean_text(getattr(entry, "published", ""))

    important = is_important(title, summary)

    prefix = feed_conf.get("prefix", "")
    if important:
        prefix = "⭐ **重要** " + prefix

    embed_title = f"⭐ {title}" if important else title

    fields = []
    if published:
        fields.append({
            "name": "Published",
            "value": trim(published, 100),
            "inline": True,
        })

    embed = {
        "title": embed_title,
        "url": link,
        "description": summary if summary else None,
        "color": 0xE74C3C if important else base_color,
        "footer": {"text": f"{hub} / {name}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }

    embed = {k: v for k, v in embed.items() if v is not None}

    return {
        "username": feed_conf.get("username", "Google Alerts"),
        "content": prefix,
        "embeds": [embed],
    }


def post_to_discord(webhook_url: str, payload) -> bool:
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=DISCORD_TIMEOUT_SECONDS,
        )

        if 200 <= response.status_code < 300:
            return True

        print(
            f"ERROR: Discord投稿失敗 status={response.status_code} body={response.text[:500]}",
            file=sys.stderr,
        )
        return False

    except requests.RequestException as exc:
        print(f"ERROR: Discord投稿中に例外が発生しました: {exc}", file=sys.stderr)
        return False


def process_feed(feed_conf, state) -> bool:
    name = feed_conf.get("name", "Unnamed feed")

    rss_url = env_value(feed_conf.get("rss_env", ""))
    webhook_url = env_value(feed_conf.get("webhook_env", ""))

    if not rss_url:
        print(f"SKIP: RSS URL未設定: {name}")
        return False

    if not webhook_url:
        print(f"SKIP: Webhook未設定: {name}")
        return False

    print(f"CHECK: {name}")

    feed = feedparser.parse(rss_url)
    entries = list(getattr(feed, "entries", []))

    if not entries:
        print(f"NO ENTRIES: {name}")
        return False

    feed_key = feed_conf.get("id") or hashlib.sha256(name.encode("utf-8")).hexdigest()

    # 初回だけ：投稿せず既読登録
    if feed_key not in state:
        if SKIP_FIRST_RUN:
            state[feed_key] = [make_entry_id(entry) for entry in entries][-MAX_SEEN_PER_FEED:]
            print(f"FIRST RUN SKIPPED: {name} / registered={len(state[feed_key])}")
            return True
        else:
            state[feed_key] = []

    seen = state.setdefault(feed_key, [])

    new_entries = []
    for entry in reversed(entries):
        entry_id = make_entry_id(entry)
        if entry_id not in seen:
            new_entries.append((entry_id, entry))

    if not new_entries:
        print(f"NO NEW: {name}")
        return False

    posted_count = 0

    for entry_id, entry in new_entries[:MAX_POSTS_PER_FEED]:
        payload = discord_embed_payload(feed_conf, entry)
        ok = post_to_discord(webhook_url, payload)

        if ok:
            seen.append(entry_id)
            posted_count += 1
            print(f"POSTED: {name} / {clean_text(getattr(entry, 'title', ''))}")
        else:
            print(f"FAILED: {name}", file=sys.stderr)

    state[feed_key] = seen[-MAX_SEEN_PER_FEED:]

    print(f"DONE: {name} / posted={posted_count}")
    return posted_count > 0


def main() -> int:
    if not FEEDS_FILE.exists():
        print("ERROR: feeds.json が見つかりません。", file=sys.stderr)
        return 1

    feeds = load_json(FEEDS_FILE, default=[])
    state = load_json(STATE_FILE, default={})

    changed = False

    for feed_conf in feeds:
        if not feed_conf.get("enabled", True):
            print(f"SKIP DISABLED: {feed_conf.get('name')}")
            continue

        try:
            changed = process_feed(feed_conf, state) or changed
        except Exception as exc:
            print(f"ERROR: {feed_conf.get('name')} / {exc}", file=sys.stderr)

    if changed:
        save_json(STATE_FILE, state)
        print("STATE UPDATED")
    else:
        print("STATE NOT CHANGED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
