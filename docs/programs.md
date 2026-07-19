# プログラム一覧

## Python

### `app.py`

- 目的: ダッシュボード（データ概要・書類種別内訳・最近の提出書類）
- 実行場所: PC / Streamlitホスティング
- 入力: `db_helper.get_db_stats()`、`get_recent_documents()`、サイドバーからの`search_companies()`
- 出力: ブラウザ画面
- 起動: `run.bat` または `python -m streamlit run app.py`
- 備考: サイドバーのクイック検索結果は`/Company?sec_code=...`へリンク

### `db_helper.py`

- 目的: SQLite接続とデータ取得ユーティリティ
- 単独実行: しない（各ページからimport）
- DBパス: `data/edinet_data.sqlite3`
- 主な関数:
  - `get_db_stats` / `get_recent_documents`
  - `get_company_list` / `search_companies` / `get_company_info`
  - `get_company_documents` / `get_key_financials` / `get_financial_details`
  - `get_multi_company_financials` / `get_screening_data`
  - `get_company_text_blocks` / `get_text_block_sections` / `search_text_blocks`
- 定数: `DOC_TYPE_NAMES`（書類種別コード→日本語名）
- キャッシュ: 一部関数に`@st.cache_data`

### `pages/01_Search.py`

- 目的: 証券コード・企業名での企業検索と全企業一覧
- 入力: 検索キーワード、`get_company_list()`
- 出力: 企業行ごとの「詳細」「テキスト」リンク、ページネーション付き一覧（50件/ページ）

### `pages/02_Company.py`

- 目的: 1社の財務・チャート・テキスト・書類一覧
- 入力: URLクエリ`sec_code`またはセレクトボックス
- 依存: plotly（`graph_objects` / `make_subplots`）
- 出力:
  - 主要財務テーブル（億円）とCSV
  - 売上・利益 / BS / CFのチャート
  - 期末選択付きテキストブロック
  - 提出書類一覧

### `pages/03_Compare.py`

- 目的: 最大5社の財務比較
- 入力: 企業マルチセレクト
- 出力:
  - 最新期の横並び指標表
  - 選択指標の推移線グラフ
  - 2社以上でレーダーチャート（指標を企業間最大値で正規化）
- 備考: 連結データがあれば連結のみ使用

### `pages/04_Screening.py`

- 目的: 最新連結期の財務条件による企業絞り込み
- 入力: 売上高・営業利益・純利益・自己資本比率・営業利益率・総資産の最小/最大
- 出力: ソート可能な結果表、`screening_result.csv`
- 算出: 自己資本比率・営業利益率はページ内計算

### `pages/05_TextBlocks.py`

- 目的: テキストブロックの横断検索・閲覧
- 入力: 証券コード、セクション、キーワード、表示件数上限（10〜200）
- 出力: ハイライト付き本文、個別`.txt`、一括CSV
- URL: `?sec_code=`でコード初期値を受け取り可能

## Windowsバッチ

### `run.bat`

- 目的: ローカルでViewerを起動
- 内容:
  - `chcp 65001`
  - リポジトリディレクトリへ移動
  - 固定パスの`python.exe -m streamlit run app.py --server.port 8502`
- 注意: Pythonの絶対パスは作成マシン向けです。別PCではパス修正か、直接`python -m streamlit ...`を使います

### `push.bat`

- 目的: 変更を一括でadd / commit / push
- 内容:
  - `git add -A`
  - 固定メッセージで`git commit`
  - `git push -u origin main`
- 注意: コミットメッセージがバッチ内に固定されているため、ドキュメント更新など別趣旨の変更には向きません。通常の`git commit`を使う方が安全です

## 設定ファイル

### `.streamlit/config.toml`

- テーマ色（primary `#1a73e8`など）
- `server.headless = true`
- `browser.gatherUsageStats = false`

### `.gitignore`

- `__pycache__/`、`*.pyc`、`.env`、`*.sqlite3.bak`
- `data/edinet_data.sqlite3`自体は無視しません

### `requirements.txt`

- streamlit>=1.30.0
- pandas>=2.1.0
- plotly>=5.18.0

## GitHub Actions

このリポジトリにワークフロー定義はありません。定期取得や自動更新は行いません。

## 含まれないもの

次の処理はコードベースに存在しません。

- EDINET API / 書類ダウンロード
- XBRLパース・主要指標抽出・テキスト抽出
- DBスキーマ作成・マイグレーション
- Google DriveやGitHub Pagesへの成果物配信
