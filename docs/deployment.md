# Deployment Guide

このMVPはStreamlitで動くPython Webアプリです。短期公開と本格運用で、適した構成が少し違います。

## 結論

まずは `Streamlit Community Cloud` または `Render` で公開するのが最短です。

Cloudflareは、現段階では以下の用途に向いています。

- 独自ドメインのDNS管理
- HTTPS、WAF、Bot対策
- 将来のフロントエンド配信
- Cloudflare Tunnelによる一時的なローカル公開

Streamlitアプリ本体はPythonサーバーとして常時動かす必要があります。Cloudflare Pages単体では、現在の `app.py` をそのまま実行できません。

## Option A: Streamlit Community Cloud

最初に公開するならこの方法が一番簡単です。

1. GitHubにこのリポジトリをpushする
2. Streamlit Community Cloudで新規アプリを作る
3. Repositoryを選ぶ
4. Main file pathに `app.py` を指定する
5. Secretsに以下を設定する

```toml
EDINET_API_KEY = "実キーをここに入れる"
DATABASE_URL = "sqlite:///data/app.sqlite"
ENV = "production"
```

注意:

- `.env` はアップロードしません。
- `.streamlit/secrets.toml` もGit管理しません。
- GitHubがPublicの場合、APIキーや取得済みEDINETファイルが入っていないことを必ず確認してください。
- Streamlit Cloudのファイル保存領域は永続保存を前提にしない方が安全です。EDINET取得結果を長く使う場合は、後続で外部DBまたはオブジェクトストレージへ移します。

## Option B: Render / Fly.io / Cloud Run

コンテナで動かす場合は、追加済みの `Dockerfile` を使えます。

ローカルでビルド確認:

```powershell
docker build -t company-report .
docker run --rm -p 8501:8501 -e EDINET_API_KEY=YOUR_KEY company-report
```

本番環境では、ホスティング側のEnvironment Variablesに以下を設定します。

```text
EDINET_API_KEY=実キー
DATABASE_URL=sqlite:///data/app.sqlite
ENV=production
```

Renderなどで永続ディスクを使う場合は、SQLite DBや取得済みファイルの保存先を永続ディスク配下に変更します。

## Option C: Cloudflareを使う場合

Cloudflareだけで現在のStreamlitアプリを直接動かすのではなく、次のどちらかが現実的です。

Cloudflare側の具体的な操作手順は [cloudflare_setup.md](cloudflare_setup.md) にまとめています。

### C-1. Cloudflare Tunnel

ローカルで起動したStreamlitを一時的に外部へ見せる方法です。デモや短時間レビュー向けです。

```powershell
streamlit run app.py
cloudflared tunnel --url http://localhost:8501
```

注意:

- PCを止めるとアプリも止まります。
- APIキーやローカルファイルの扱いに注意してください。
- 常設公開には向きません。

### C-2. Cloudflare + 外部Pythonホスティング

本格公開では、PythonアプリをRender/Fly/Cloud Runなどで動かし、Cloudflareはドメイン、HTTPS、WAF、キャッシュ制御の前面に置きます。

将来構成:

```text
Cloudflare DNS / WAF
  -> Streamlit MVP または FastAPI Backend
  -> PostgreSQL / SQLite永続ディスク
  -> R2などのファイル保存
```

さらに本格化する場合は、Streamlitを管理画面・試作用に残し、一般ユーザー向けWebアプリは以下に分けます。

```text
Cloudflare Pages: React / Next.js フロントエンド
Cloud Run / Render: FastAPI バックエンド
PostgreSQL: 財務データと取得履歴
R2 / S3: EDINET ZIP, XBRL, 生成レポート
```

## デプロイ前チェック

```powershell
pytest
git status --short
```

含めないもの:

- `.env`
- `.streamlit/secrets.toml`
- `output/`
- `outputs/`
- `work/`
- SQLite DB
- 生成済みWord/PDF/Excel
- EDINETから取得したZIP/XBRL/PDF
- 講義資料PDF

## 公開後の最初の確認

1. トップ画面が表示される
2. プリセットで比較できる
3. Wordレポートが生成できる
4. `EDINET_API_KEY` が設定済み表示になる
5. 証券コード検索でEDINETの書類一覧が取得できる
6. APIキーや取得ファイルが画面やGitHubに露出していない
