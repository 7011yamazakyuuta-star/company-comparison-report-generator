# ChatGPT Pro Review Prompt

以下をChatGPT Pro / GPT-5.5 Proに貼り付けて、現状の設計レビューや次の実装優先度の相談に使えます。

```markdown
あなたは、財務分析、EDINET/XBRL、Python Webアプリ設計、大学課題レポート作成支援に詳しいシニアアドバイザーです。

日本の上場企業比較レポート生成ツールを開発しています。投資助言ではなく、大学課題・学習・企業分析レポート作成支援が目的です。「買い」「売り」「投資すべき」などの売買推奨表現は禁止です。

## 現状

- Python / Streamlit / SQLite / pandas / matplotlib / python-docx / PyYAML / pytestでMVPを作成済み
- サンプルCSVで2社以上の日本上場企業を比較可能
- Wordレポート生成済み
- EDINET APIキーは取得済み
- EDINET APIから書類一覧を取得し、CSV ZIPを保存する段階まで実装中
- 取得済みEDINETファイルから財務データへ正規化する処理はこれから
- UIはApple風・ライト基調・初心者向けのオートマ作成モードを強化中
- 課題モードと汎用分析モードを分けている
- 条件、プリセット、業種判定はYAML管理

## 目的

1. EDINET API取得を本格化したい
2. XBRL/CSV解析を安定させたい
3. 財務分析アルゴリズムを高度化したい
4. Web公開できる状態にしたい
5. 大学課題の必須部分と＋α分析を明確に満たしたい

## 必須分析

- 企業を2社以上選ぶ
- 条件を満たすか確認する
- 事業内容を説明する
- 財務諸表の主要数値を比較する
- 最後に経営状況を要約する

## ＋α分析

- ROA / ROE分解
- 損益分岐点分析
- 安全余裕率
- 営業レバレッジ
- 売上増減分析
- 利益増減分析
- 4P / 4C分析
- 顧客関係分析
- バリューチェーン分析
- FCF分析
- PER / PBR比較
- 将来シナリオ分析

## 特に相談したいこと

以下を、優先順位付きでレビューしてください。

1. 現状MVPから本格Webアプリへ進める際の最短ルート
2. Streamlitを維持するべきか、FastAPI + React/Next.jsへ分けるべきか
3. EDINET API / XBRL / CSV解析の堅牢な設計
4. SQLiteからPostgreSQLやCloudflare R2等へ移行するタイミング
5. 財務分析アルゴリズムで足りない観点
6. 大学課題として評価されやすいレポート構成
7. 投資助言にならない表現ルール
8. テスト戦略
9. デプロイ戦略
10. 次のIssueとして切るべき作業

## 回答形式

以下の形式で答えてください。

### 総評

### 重大リスク

### 次にやるべき順番

### EDINET / XBRL設計案

### 分析アルゴリズム強化案

### Webアプリ化の設計案

### 大学課題として強い見せ方

### 禁止すべき表現・注意文

### 具体的なIssue案

### 追加で確認したいファイル

必要があれば、README、production_roadmap.md、deployment.md、生成済みWordレポート、LLM用プロンプト、主要コードの抜粋を追加で渡します。
```

## 一緒に渡すと良いもの

- `README.md`
- `docs/production_roadmap.md`
- `docs/deployment.md`
- `docs/course_framework.md`
- 生成済みWordレポート
- アプリ画面スクリーンショット
- `src/edinet_client.py`
- `src/edinet_lookup.py`
- `src/analysis_engine.py`
- `src/report_writer.py`

