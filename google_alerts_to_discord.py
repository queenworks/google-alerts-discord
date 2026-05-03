#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Googleアラート RSS → Discord Webhook 配信用スクリプト

特徴:
- Notionなし
- 複数RSS対応
- 複数Discordサーバー / チャンネル対応
- feeds.json に追加するだけでRSSを増やせる
- 重複投稿防止あり
- GitHub Actionsで1日2回など定期実行できる

使い方:
1. feeds.json を編集
2. GitHub Secrets に RSS URL と Discord Webhook URL を登録
3. GitHub Actions を実行
"""

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import feedparser
import requests


FEEDS_FILE = Path("feeds.json")
STATE_FILE = Path("state/google_alerts_seen.json")

# 1回の実行で、1つのRSSから最大何件まで投稿するか
# たくさん溜まっていた時の大量投稿を防ぐためです。
MAX_POSTS_PER_FEED = 3

# RSSごとに保存する既読IDの最大数
# 古いものは自動的に捨てます。
MAX_SEEN_PER_FEED = 500

DISCORD_TIMEOUT_SECONDS = 20


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"ERROR: JSONの読み込みに失敗しました: {path}", file=sys.stderr)
        raise


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def env_value(name: str) -> str:
    """
    GitHub Secrets / 環境変数から値を取得します。
    未設定なら空文字を返します。
    """
    if not name:
        return ""
    return os.environ.get(name, "").strip()


def make_entry_id(entry: Any) -> str:
    """
    RSS記事を識別するIDを作ります。
    GoogleアラートRSSでは entry.id があることが多いですが、
    念のため link/title/published からも作れるようにします。
    """
    raw = (
        getattr(entry, "id", "")
        or getattr(entry, "link", "")
        or f"{getattr(entry, 'title', '')}|{getattr(entry, 'published', '')}"
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def trim(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def discord_embed_payload(feed_conf: Dict[str, Any], entry: Any) -> Dict[str, Any]:
    """
    Discordに投げるEmbedを作ります。
    """
    hub = feed_conf.get("hub", "Google Alerts")
    name = feed_conf.get("name", "Alert")
    color = feed_conf.get("color", 0x3498DB)

    title = trim(getattr(entry, "title", "No title"), 250)
    link = getattr(entry, "link", "")

    summary = getattr(entry, "summary", "") or ""
    summary = trim(summary.replace("\n", " "), 500)

    published = getattr(entry, "published", "")
    source_title = ""
    try:
        source_title = entry.get("source", {}).get("title", "")
    except Exception:
        source_title = ""

    fields = []
    if source_title:
        fields.append({"name": "Source", "value": trim(source_title, 100), "inline": True})
    if published:
        fields.append({"name": "Published", "value": trim(published, 100), "inline": True})

    embed = {
        "title": title,
        "url": link,
        "description": summary if summary else None,
        "color": int(color),
        "footer": {"text": f"{hub} / {name}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fields": fields,
    }

    # Noneの項目を消します
    embed = {k: v for k, v in embed.items() if v is not None}

    return {
        "username": feed_conf.get("username", "Google Alerts"),
        "content": feed_conf.get("prefix", ""),
        "embeds": [embed],
    }


def post_to_discord(webhook_url: str, payload: Dict[str, Any]) -> bool:
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


def process_feed(feed_conf: Dict[str, Any], state: Dict[str, Any]) -> bool:
    """
    1つのRSSを処理します。
    新しい記事が投稿された場合は True を返します。
    """
    name = feed_conf.get("name", "Unnamed feed")

    rss_url = env_value(feed_conf.get("rss_env", ""))
    webhook_url = env_value(feed_conf.get("webhook_env", ""))

    if not rss_url:
        print(f"SKIP: RSS URL未設定: {name} / rss_env={feed_conf.get('rss_env')}")
        return False

    if not webhook_url:
        print(f"SKIP: Webhook未設定: {name} / webhook_env={feed_conf.get('webhook_env')}")
        return False

    print(f"CHECK: {name}")

    feed = feedparser.parse(rss_url)

    if getattr(feed, "bozo", False):
        print(f"WARNING: RSSの解析で警告があります: {name} / {feed.get('bozo_exception')}")

    entries = list(getattr(feed, "entries", []))
    if not entries:
        print(f"NO ENTRIES: {name}")
        return False

    feed_key = feed_conf.get("id") or hashlib.sha256(name.encode("utf-8")).hexdigest()
    seen: List[str] = state.setdefault(feed_key, [])

    # 古い順に投稿したいので、RSSの並びを反転します。
    # GoogleアラートRSSは新しい順で来ることが多いです。
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
            print(f"POSTED: {name} / {getattr(entry, 'title', '')}")
        else:
            # 投稿失敗した記事は既読にしません。
            print(f"FAILED: {name} / {getattr(entry, 'title', '')}", file=sys.stderr)

    # 既読リストを軽く保ちます。
    state[feed_key] = seen[-MAX_SEEN_PER_FEED:]

    print(f"DONE: {name} / posted={posted_count}")
    return posted_count > 0


def main() -> int:
    if not FEEDS_FILE.exists():
        print("ERROR: feeds.json が見つかりません。", file=sys.stderr)
        return 1

    feeds = load_json(FEEDS_FILE, default=[])
    state = load_json(STATE_FILE, default={})

    if not isinstance(feeds, list):
        print("ERROR: feeds.json は配列形式にしてください。", file=sys.stderr)
        return 1

    changed = False

    for feed_conf in feeds:
        try:
            if not feed_conf.get("enabled", True):
                print(f"SKIP DISABLED: {feed_conf.get('name', 'Unnamed feed')}")
                continue

            changed = process_feed(feed_conf, state) or changed

        except Exception as exc:
            print(
                f"ERROR: feed処理中に例外が発生しました: {feed_conf.get('name', 'Unnamed feed')} / {exc}",
                file=sys.stderr,
            )

    if changed:
        save_json(STATE_FILE, state)
        print("STATE UPDATED")
    else:
        print("STATE NOT CHANGED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
