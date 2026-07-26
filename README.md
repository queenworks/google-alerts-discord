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

まだチャンネルを作っていない場合は、先にDiscordサーバー・チャンネルを作り、
それぞれの投稿先チャンネルでWebhookを作ります。

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

`feeds.json` に書かれた `rss_env` / `webhook_env` の名前でSecretを登録します。

内容を公開したくないフィード（銘柄名など）は、`hub` / `name` / `username` / `prefix` を
`feeds.json` に直接書かず、代わりに `hub_env` / `name_env` / `username_env` / `prefix_env`
で参照するSecret名を指定してください。実際の表示名やアラート文言はSecrets側にだけ置かれ、
`feeds.json`には残りません。

## GoogleアラートRSSの作り方

Googleアラートでアラートを作成し、配信先を「RSSフィード」にします。

そのRSS URLをコピーして、GitHub Secrets に登録します。

## RSSを増やす方法

`feeds.json` に1ブロック追加します。

公開してよい内容の例:

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

非公開にしたい内容の例（表示名もSecrets経由にする）:

```json
{
  "id": "watch-4",
  "enabled": true,
  "hub_env": "WATCH4_HUB",
  "name_env": "WATCH4_NAME",
  "rss_env": "WATCH4_RSS",
  "webhook_env": "WATCH4_WEBHOOK",
  "username_env": "WATCH4_USERNAME",
  "prefix_env": "WATCH4_PREFIX",
  "color": 3447003
}
```

この場合、GitHub Secretsに `WATCH4_RSS` `WATCH4_WEBHOOK` `WATCH4_HUB` `WATCH4_NAME`
`WATCH4_USERNAME` `WATCH4_PREFIX` を登録します。

## 実行タイミング

`.github/workflows/google_alerts_discord.yml` では、1日3回にしています。

```text
JST 05:00
JST 13:00
JST 19:00
```

変更したい場合は cron を変更します。

## 重複投稿防止

投稿済みの記事IDを `state/google_alerts_seen.json` に保存します。
キーは各フィードの `id` です。

GitHub Actionsが実行後にこのファイルを自動コミットします。
これにより、次回実行時に同じ記事を再投稿しません。

## 最初の実行について

初回はそのフィードの記事を投稿せず、既読登録だけを行います。
2回目以降の実行から新着記事を投稿します。

1回の実行で投稿する件数は、`google_alerts_to_discord.py` の以下で制限しています。

```python
MAX_POSTS_PER_FEED = 21
```
