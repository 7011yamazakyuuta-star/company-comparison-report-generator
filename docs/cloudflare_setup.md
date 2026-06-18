# Cloudflare Setup Guide

この手順は、Cloudflare側の設定を人間が進めるためのガイドです。

## まず決めること

現在のアプリは `Streamlit` で動くPython Webアプリです。Cloudflare Pages単体では `app.py` をそのまま実行できません。

おすすめは次のどちらかです。

| 目的 | 推奨構成 |
|---|---|
| まず公開URLを作りたい | Streamlit Cloud / Render でアプリを動かし、Cloudflare DNSで独自ドメインを向ける |
| いまのローカル画面を一時的に外部共有したい | Cloudflare Tunnelで `localhost:8501` を公開する |
| 将来の本格Webアプリ | Cloudflare Pages + FastAPI Backend + DB + R2 |

最初は **Streamlit CloudまたはRender + Cloudflare DNS** が一番わかりやすいです。

## 用語

- **ドメイン**: `example.com` のような住所
- **サブドメイン**: `app.example.com` や `report.example.com`
- **DNS**: ドメインを公開先サーバーへ向ける設定
- **CNAME**: `app.example.com` を `your-app.onrender.com` などへ向けるDNSレコード
- **Proxied**: Cloudflareを経由してアクセスさせる設定
- **DNS only**: Cloudflareを経由せず、DNSだけ使う設定
- **Full (strict)**: ブラウザとCloudflare、Cloudflareと公開先サーバーの両方をHTTPSでつなぐ設定
- **Tunnel**: ローカルPCや非公開サーバーをCloudflare経由で外に見せる仕組み

## Route A: 外部ホスティング + Cloudflare DNS

常設公開に向いている方法です。

### 1. アプリを先に公開する

まずStreamlit Cloud、Render、Fly.io、Cloud Runなどでアプリを公開します。

公開先で設定する環境変数:

```text
EDINET_API_KEY=実キー
DATABASE_URL=sqlite:///data/app.sqlite
ENV=production
```

確認:

- 公開URLでトップ画面が開く
- Wordレポート生成ができる
- EDINET取得画面でAPIキーが「設定済み」になる
- GitHubに `.env` や生成済みファイルが入っていない

### 2. Cloudflareにドメインを追加する

1. Cloudflare Dashboardを開く
2. `Add a domain` または `Add site` を選ぶ
3. 使いたいドメインを入力する
4. プランを選ぶ。最初はFreeで十分
5. 既存DNSレコードの読み込み結果を確認する
6. Cloudflareが表示するネームサーバーを控える
7. ドメインを買った管理画面で、ネームサーバーをCloudflare指定のものへ変更する
8. Cloudflare側で有効化されるまで待つ

反映は数分から数時間かかることがあります。

### 3. アプリ用サブドメインを作る

例: `app.example.com` で公開する場合。

Cloudflare Dashboard:

1. 対象ドメインを開く
2. `DNS` > `Records`
3. `Add record`
4. 以下を入力

```text
Type: CNAME
Name: app
Target: 公開先ホスティングが指定するCNAME先
Proxy status: Proxied
TTL: Auto
```

例:

```text
app.example.com -> your-app.onrender.com
```

注意:

- 公開先ホスティング側にも、同じカスタムドメイン `app.example.com` を登録してください。
- ホスティング側が指定するCNAME先がある場合は、それを優先してください。
- うまく表示されない場合は、一時的に `DNS only` にして、Cloudflare経由かホスティング側かを切り分けます。

### 4. SSL/TLSを設定する

Cloudflare Dashboard:

1. 対象ドメインを開く
2. `SSL/TLS` > `Overview`
3. 暗号化モードを `Full (strict)` にする

`Full (strict)` は、公開先サーバーが有効なHTTPS証明書を持っている場合に使います。Renderや一般的なホスティングのHTTPS公開URLなら通常この設定で進めます。

避けたい設定:

- `Off`: HTTPSなしになる
- `Flexible`: Cloudflareから公開先サーバーまでがHTTPになり、リダイレクトループやセキュリティ問題の原因になりやすい

### 5. WebSocketを確認する

Streamlitは画面更新にWebSocketを使います。CloudflareはプロキシされたWebSocket接続を追加設定なしでサポートします。

確認方法:

- `app.example.com` を開く
- ボタンを押して画面が反応する
- Streamlitの右上に接続エラーが出ない
- 画面が何度も再接続しない

もしおかしい場合:

1. DNSレコードを一時的に `DNS only` にする
2. 直るならCloudflare側のWAF、Bot Fight Mode、キャッシュ、ルールを疑う
3. 直らないなら公開先ホスティング側の設定を確認する

### 6. キャッシュは弱めにする

このアプリは静的サイトではなく、ユーザー操作で状態が変わるWebアプリです。

最初はCloudflareの強いキャッシュ設定を入れないでください。

必要なら後で:

- `Cache Rules`
- 対象: `app.example.com/*`
- Action: `Bypass cache`

にします。

### 7. WAF / Bot対策は最初は控えめ

最初から強いBot対策を入れると、Streamlitの通信やファイルダウンロードが不安定になることがあります。

最初のおすすめ:

- WAF managed rules: 標準のまま
- Bot Fight Mode: 問題が出たらOFFで切り分け
- Rate limiting: EDINET取得やWord生成のボタン連打対策として後で追加

### 8. 限定公開したい場合

まだ本番公開ではなく、本人・先生・レビュー担当だけに見せたい場合は、Cloudflare Accessを使うと安全です。

流れ:

1. Cloudflare Zero Trustを開く
2. `Access` > `Applications`
3. `Add an application`
4. `Self-hosted` を選ぶ
5. Application domainに `app.example.com` を入れる
6. Policyで自分のメールアドレスや許可したメールだけ通す

これで、アプリに入る前にCloudflareのログイン画面を挟めます。

## Route B: Cloudflare Tunnelでローカルを一時公開

PCで起動している `http://localhost:8501` を、Cloudflare経由で外から見られるようにする方法です。

向いている用途:

- ChatGPTや外部レビューに一時的に見せたい
- 先生や友人に短時間だけ確認してもらいたい
- 本格デプロイ前の確認

向いていない用途:

- 常設公開
- PCを閉じても動かしたい運用
- 多人数利用

### 1. ローカルでStreamlitを起動

```powershell
C:\Users\7011y\AppData\Local\Programs\Python\Python310\python.exe -m streamlit run app.py --server.port 8501
```

ブラウザで確認:

```text
http://localhost:8501
```

### 2. Cloudflare Tunnelを作る

Cloudflare Dashboard:

1. `Zero Trust` を開く
2. `Networks` > `Tunnels`
3. `Create a tunnel`
4. Connector typeは `Cloudflared`
5. Tunnel名を入れる

例:

```text
company-report-local
```

6. Windows用の `cloudflared` 実行コマンドが表示されるので、PowerShellに貼って実行する
7. Connectorが接続済みになったら次へ進む

### 3. Public hostnameを設定する

Tunnel設定でPublic hostnameを追加します。

```text
Subdomain: app
Domain: example.com
Path: 空欄
Type: HTTP
URL: localhost:8501
```

保存すると、`https://app.example.com` からローカルのStreamlitへアクセスできます。

注意:

- PCとStreamlitとcloudflaredが起動している間だけ使えます。
- `.env` のAPIキーは画面に出さないこと。
- 共有前に生成物やローカルファイルの扱いを確認してください。

## 初回チェックリスト

Cloudflare設定後、以下を確認します。

- `https://app.example.com` が開く
- オートマ作成画面が表示される
- プリセット比較が動く
- Wordレポート生成ボタンが動く
- EDINET取得画面でAPIキーが「設定済み」になる
- 証券コード検索でEDINET書類一覧を取得できる
- 画面右上やコンソールにWebSocket接続エラーが出ていない
- GitHubに `.env`、`.streamlit/secrets.toml`、生成済みWord、SQLite DB、EDINET ZIPが入っていない

## トラブル時の切り分け

| 症状 | 確認すること |
|---|---|
| 画面が開かない | DNSレコード、ホスティング側のカスタムドメイン登録、SSL証明書 |
| リダイレクトが止まらない | SSL/TLSが `Flexible` になっていないか |
| ボタンを押しても反応しない | WebSocket、WAF、Bot対策、キャッシュ |
| EDINETだけ動かない | デプロイ先Secretsの `EDINET_API_KEY` |
| Word生成が落ちる | ホスティングのメモリ、書き込み可能ディレクトリ、生成先 |
| Tunnelが切れる | PCのスリープ、Streamlit停止、cloudflared停止 |

## おすすめの進め方

1. まずGitHubへ現在のMVPをpushする
2. Streamlit CloudまたはRenderで公開する
3. 公開URLで動作確認する
4. Cloudflareにドメインを追加する
5. `app.example.com` を公開先へ向ける
6. SSL/TLSを `Full (strict)` にする
7. 動作確認後、必要ならCloudflare Accessで限定公開する
8. EDINET本格取得と分析エンジン高度化へ進む

