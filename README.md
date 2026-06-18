# Company Comparison Report Generator

日本の上場企業を比較し、大学課題条件のチェック、財務指標分析、グラフ生成、日本語Wordレポート出力を行うローカルMVPです。

技術スタックは Python, Streamlit, SQLite, pandas, matplotlib, python-docx, PyYAML, pytest です。通常表示はサンプルCSVを基準に動作し、EDINET APIは書類一覧取得、CSV ZIP取得、主要財務タグ候補の抽出、Word生成時の候補反映まで対応しています。網羅的なXBRL/CSV解析と全勘定科目の正規化は今後の拡張対象です。

## MVPでできること

- 2社以上の日本上場企業を比較する
- 大学課題モードで上場日、上場後年数、同業種、除外業種をチェックする
- 汎用分析モードで金融・医療分野も含めた比較を許可する
- JPX業種一致、事業テーマ、広義セクターの3種類で業種判定する
- 売上高、営業利益率、ROA、ROE、自己資本比率、FCFなどを計算する
- 欠損値や0除算を「推定不可」として扱う
- 売上高推移、営業利益率推移、ROA/ROE推移、自己資本比率推移、営業CF/FCF推移のPNGグラフを生成する
- 表とグラフ入りの日本語Wordレポートを生成する
- EDINET APIキーがある場合、指定日付の書類一覧を取得してSQLiteに保存する
- EDINETの保存済み一覧を検索し、有価証券報告書のCSV ZIPを1件ずつ取得する
- 取得したCSV ZIPから主要財務タグ候補を抽出し、SQLiteへ保存して分析用データ候補を確認する
- 詳細設定では、サンプルCSVを基準にEDINET抽出候補を同一証券コード・年度だけ優先する検証モードを選べる
- `data/company_master/edinet_company_directory.csv` にEDINET提出者由来の軽量企業候補を同梱する
- `scripts/build_edinet_company_directory.py` でEDINET企業候補辞書を再生成できる
- OSやブラウザのダークテーマに左右されにくいライト基調のStreamlit画面で操作する

## セットアップ

```powershell
git clone https://github.com/YOUR_NAME/company-comparison-report-generator.git
cd company-comparison-report-generator
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

既存のPython環境を使う場合は、仮想環境作成を省略しても構いません。ただし、このPCでは `python` がPython 3.11を指している一方、StreamlitなどはPython 3.10側に入っている場合があります。迷ったらPython 3.10を明示してください。

## 環境変数

`.env.example` を参考に、必要に応じてローカルだけに `.env` を作成してください。実キーはGitに含めません。

```text
EDINET_API_KEY=
DATABASE_URL=sqlite:///data/app.sqlite
ENV=local
```

`EDINET_API_KEY` が未設定でも、サンプルCSVとpytestは動作します。

Streamlit Community Cloudなどに公開する場合は、`.env` ではなくデプロイ先のSecretsまたは環境変数に `EDINET_API_KEY` を設定してください。Streamlit Secretsの例は `.streamlit/secrets.example.toml` にあります。

## デプロイ

短期公開はStreamlit Community CloudまたはRenderが最短です。Cloudflareは現時点ではDNS、HTTPS、WAF、Cloudflare Tunnel、将来のフロントエンド配信に使うのが自然です。

詳しい手順は [docs/deployment.md](docs/deployment.md) を参照してください。

Cloudflare側のDNS、SSL/TLS、Tunnel、Access設定を進める場合は [docs/cloudflare_setup.md](docs/cloudflare_setup.md) を参照してください。

コンテナデプロイ向けに `Dockerfile` と `.dockerignore` も用意しています。

## 本格化ロードマップ

EDINET API取得、XBRL/CSV解析、分析アルゴリズム高度化、Webアプリ化の進め方は [docs/production_roadmap.md](docs/production_roadmap.md) に整理しています。

ChatGPT Pro / GPT-5.5 Proへ設計レビューを依頼する場合は、[docs/chatgpt_pro_review_prompt.md](docs/chatgpt_pro_review_prompt.md) のプロンプトを使えます。

## EDINET書類一覧の取得

APIキーを `.env` に保存したあと、Streamlitの `EDINET取得` タブから1日分の書類一覧を取得できます。

取得の最初の対象は「書類一覧とメタデータ」です。大量のXBRL/CSV/PDFダウンロードはまだ行いません。
保存済み一覧では、会社名、EDINETコード、docID、証券コードで検索できます。まずは「有価証券報告書のみ」「CSVありのみ」で絞り込み、必要な書類を1件ずつ `output/raw_filings/` に保存します。

EDINET APIは証券コードを直接投げる検索APIではなく、日付ごとの書類一覧を取得するAPIです。このアプリでは、入力した証券コードについて直近N日分の書類一覧を取得し、EDINETの `secCode` で絞り込みます。

```text
証券コード入力
→ EDINET書類一覧を日付ごとに取得
→ secCodeで対象企業を抽出
→ 有価証券報告書 / CSVありで絞り込み
→ CSV ZIPを保存
→ 現行アルゴリズムで比較レポート生成
```

標準設定では財務指標計算にサンプルCSVを使います。詳細設定のレポート画面では、保存済みEDINET抽出候補を同一証券コード・年度だけサンプルCSVより優先する検証モードを選べます。Word生成時にも選択企業のEDINET書類を確認し、抽出できた主要財務候補を優先候補として利用します。網羅的な実データ反映は、XBRL/CSV解析強化の拡張対象です。

ローカルで疎通確認したい場合は、キーを表示せずに件数だけ確認できます。

```powershell
python -c "from datetime import date, timedelta; from src.edinet_client import EdinetClient, extract_document_rows; d=date.today()-timedelta(days=1); rows=extract_document_rows(EdinetClient().fetch_documents(d)); print(len(rows))"
```

取得結果はSQLiteの `edinet_filings` テーブルに保存されます。DBファイルはGitHubに含めません。

企業検索の候補数を広げたい場合は、ローカルで以下を実行するとEDINET提出者メタデータから軽量な企業候補CSVを再生成できます。APIキーは `.env` または環境変数から読みます。
```powershell
python scripts\build_edinet_company_directory.py --days 730
```

このCSVは提出者名・証券コード・EDINETコードの検索補助用です。JPX業種や上場日は未分類の候補もあるため、大学課題モードでは条件表と警告を確認してください。
書類本体のCSV ZIPもGitHubには含めません。

## 起動方法

```powershell
.\scripts\run_app.ps1
```

または、Windowsで `run_app.bat` を実行します。直接コマンドで起動する場合は以下です。

```powershell
C:\Users\7011y\AppData\Local\Programs\Python\Python310\python.exe -m streamlit run app.py
```

ブラウザで `http://localhost:8501` を開きます。

## サンプルCSVでの実行

以下のCSVがMVPの入力データです。

- `data/company_master/sample_company_master.csv`
- `data/sample_financials/sample_financials.csv`
- `data/sample_financials/sample_market_data.csv`
- `data/manual_kpis/sample_manual_kpis.csv`

アプリ起動後、サイドバーでプリセットを選び、「分析してWordレポートを生成」を押すと、Wordレポートとグラフが `output/` 配下に生成されます。

## Wordレポート生成

生成物はGit管理しません。

- Wordレポート: `output/reports/`
- グラフPNG: `output/charts/`
- EDINET等の未加工ファイル: `output/raw_filings/`
- ログ: `output/logs/`

レポートには、表紙、課題対応表、条件適合表、企業選定理由、事業内容、講義フレームワーク、主要財務数値表、財務指標表、グラフ、収益性分析、財務安定性分析、キャッシュフロー分析、＋α分析、総合比較、結論、参考資料、欠損データ注記を含みます。

## プリセット一覧

- `friend_cafe_theme`: 3543 コメダHD、3087 ドトール・日レスHD。`business_theme` 比較。カフェ・喫茶テーマでは比較できますが、JPX業種は卸売業と小売業で一致しないため、課題モードでは警告します。
- `strict_cafe_retail`: 3087 ドトール・日レスHD、3395 サンマルクHD。`strict_jpx_industry` 比較。
- `komeda_franchise_wholesale`: 3543 コメダHD、3038 神戸物産。`strict_jpx_industry` 比較。
- `airline_assignment`: 9201 日本航空、9206 スターフライヤー、9204 スカイマーク。`strict_jpx_industry` 比較。日本航空は2012年の再上場注記を扱います。
- `airline_general`: 9201 日本航空、9202 ANA HD、9206 スターフライヤー、9204 スカイマーク。汎用モード向け。ANA HDは大学課題モードでは上場日条件に警告が出ます。

## 分析モード

大学課題モード:

- 2000-04-01以降に上場
- 上場後3年以上
- 同じ業種から2社以上
- 銀行、証券、保険、その他金融、医薬品・医療分野を除外
- `strict_jpx_industry` を標準とし、`business_theme` と `broad_sector` は警告付きで扱う

汎用分析モード:

- 金融・医療分野も分析対象にできます
- 課題条件の除外制約より、比較分析の汎用性を優先します

## 業種判定モード

- `strict_jpx_industry`: JPX業種が一致するかを判定します。大学課題モードのデフォルトです。
- `business_theme`: カフェ、航空、外食など事業テーマで比較します。課題モードでは警告します。
- `broad_sector`: 食関連、店舗ビジネス、運輸など広めの分類で比較します。課題モードでは警告します。

## 講義資料の扱い

講義資料PDFそのものはリポジトリに含めません。必要な内容は [docs/course_framework.md](docs/course_framework.md) に要約として残します。

## テスト

```powershell
pytest
```

GitHub Actionsでも、`EDINET_API_KEY` が空の状態でサンプルCSVだけを使ってpytestを実行します。

## GitHub初回push手順

GitHubで空のrepositoryを作成してください。Publicで運用する場合は、`.env` や取得済みEDINETファイルが含まれないことを必ず確認してからpushします。

- Repository name: `company-comparison-report-generator`
- Add README: OFF
- Add .gitignore: OFF
- License: None

その後、ローカルで以下を実行します。

```powershell
git remote add origin https://github.com/YOUR_NAME/company-comparison-report-generator.git
git push -u origin main
```

## GitHubに含めるもの

- `app.py`
- `README.md`
- `AGENTS.md`
- `requirements.txt`
- `.env.example`
- `.github/workflows/tests.yml`
- `config/`
- `src/`
- `tests/`
- `docs/`
- `data/company_master/sample_company_master.csv`
- `data/sample_financials/sample_financials.csv`
- `data/sample_financials/sample_market_data.csv`
- `data/manual_kpis/sample_manual_kpis.csv`

## GitHubに含めないもの

- `.env`
- APIキーや認証情報
- 講義資料PDF
- 生成されたWord/PDF/Excel
- `output/reports/`
- `output/charts/`
- `output/raw_filings/`
- `output/logs/`
- `data/raw/`
- `data/private/`
- SQLite DB
- EDINETから取得した大量ファイル

## 注意

本ツールは学習目的の企業比較レポート生成MVPです。投資助言、株式売買の推奨、金融商品の勧誘を目的としません。
