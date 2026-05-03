# Google Alerts to Discord

GoogleアラートのRSSをDiscordへ自動配信する仕組みです。

## 構成

```text
Googleアラート RSS
↓
GitHub Actions
↓
Python
↓
Discord Webhook
```

Notionは使いません。

## 入っているファイル

```text
google_alerts_to_discord.py
feeds.json
requirements.txt
.github/workflows/google_alerts_discord.yml
state/.gitkeep
```

## 事前に作るもの

### Discord側

まだチャンネルを作っていない場合は、先に以下を作ります。

- 4K Hub（投資情報Hub）
- 🌏 Weather Bosai Hub（気象防災ハブ）
- Fireworks Hub（花火ハブ）

それぞれのサーバー、またはチャンネルで Webhook を作ります。

Discordのチャンネル設定から、

```text
連携サービス
↓
ウェブフック
↓
新しいウェブフック
↓
Webhook URLをコピー
```

## GitHub Secrets に登録するもの

GitHubのリポジトリで、

```text
Settings
↓
Secrets and variables
↓
Actions
↓
New repository secret
```

以下を登録します。

### 4K Hub

```text
RSS_4K_INVEST
DISCORD_4K_WEBHOOK
```

### Weather Bosai Hub

```text
RSS_WEATHER_BOSAI
DISCORD_WEATHER_BOSAI_WEBHOOK
```

### Fireworks Hub

```text
RSS_FIREWORKS
DISCORD_FIREWORKS_WEBHOOK
```

## GoogleアラートRSSの作り方

Googleアラートでアラートを作成し、配信先を「RSSフィード」にします。

そのRSS URLをコピーして、GitHub Secrets に登録します。

## RSSを増やす方法

`feeds.json` に1ブロック追加します。

例:

```json
{
  "id": "fireworks-akita",
  "enabled": true,
  "hub": "Fireworks Hub（花火ハブ）",
  "name": "秋田 花火 Googleアラート",
  "rss_env": "RSS_FIREWORKS_AKITA",
  "webhook_env": "DISCORD_FIREWORKS_WEBHOOK",
  "username": "Fireworks Hub Alerts",
  "prefix": "🎆 **Fireworks Hub / 秋田 花火アラート**",
  "color": 15105570
}
```

その場合、GitHub Secrets に以下を追加します。

```text
RSS_FIREWORKS_AKITA
```

同じDiscordチャンネルへ流すなら、`webhook_env` は既存の `DISCORD_FIREWORKS_WEBHOOK` のままでOKです。

## 実行タイミング

`.github/workflows/google_alerts_discord.yml` では、1日2回にしています。

```text
JST 07:30
JST 19:30
```

変更したい場合は cron を変更します。

## 重複投稿防止

投稿済みの記事IDを `state/google_alerts_seen.json` に保存します。

GitHub Actionsが実行後にこのファイルを自動コミットします。
これにより、次回実行時に同じ記事を再投稿しません。

## 最初の実行について

初回はRSS内の新着記事を最大3件ずつ投稿します。

大量投稿を避けるため、1つのRSSにつき最大3件に制限しています。
変更したい場合は `google_alerts_to_discord.py` の以下を編集します。

```python
MAX_POSTS_PER_FEED = 3
```
