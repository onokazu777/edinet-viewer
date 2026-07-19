# 運用・障害対応

## 通常運用

このリポジトリは表示アプリです。PCまたはStreamlit環境で起動し、同梱の`data/edinet_data.sqlite3`を読みます。GitHub Actionsによる日次更新はありません。

確認先:

- リポジトリ: https://github.com/onokazu777/edinet-viewer
- ローカルUI: http://localhost:8502

データ更新が必要な場合は、リポジトリ外で生成したSQLiteを`data/edinet_data.sqlite3`へ置き換え、必要ならGitへコミットします。

## 起動

依存インストール:

```powershell
pip install -r requirements.txt
```

推奨起動:

```powershell
.\run.bat
```

`run.bat`のPythonパスが環境と合わない場合:

```powershell
python -m streamlit run app.py --server.port 8502
```

停止は、起動したターミナルでCtrl+Cするか、Streamlitプロセスを終了します。

## 成功確認

1. ホームに「登録企業数」「書類数」「財務データ」「テキストブロック」「データ期間」が出る
2. 「最近の提出書類」に行が表示される
3. 企業検索で既知の証券コード（例: 7203）がヒットする
4. 企業詳細で財務表または「まだ解析されていません」のいずれかが意図どおり出る
5. スクリーニングで対象企業数が0でない

## よくある障害

### データベース接続エラー / DBが見つからない

ホームまたは`db_helper.get_connection()`で停止します。

確認:

1. `data/edinet_data.sqlite3`がリポジトリ直下の`data/`にあるか
2. カレントディレクトリではなく、`db_helper.py`基準の相対パスになっているか（配置場所を動かしていないか）
3. クローン時にLFSや部分クローンで大きなファイルが欠けていないか

対処: 正しいSQLiteを`data/edinet_data.sqlite3`として配置し、アプリを再起動します。

### `run.bat`が起動しない

主な原因:

- バッチ内の`python.exe`絶対パスが存在しない
- `streamlit`未インストール
- ポート8502が使用中

対処:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.port 8502
```

別ポート例:

```powershell
python -m streamlit run app.py --server.port 8503
```

### 財務やテキストが空

DBに企業の`documents`はあるが、`key_financials`や`text_blocks`が無い（または未解析）場合があります。画面上は「まだ解析されていません」「まだ抽出されていません」と出ます。Viewer側のバグではなく、投入データの状態です。

また`financials`テーブルが無くても、主要指標ビューがあれば企業詳細の主要表・チャートは動作します。

### DBを差し替えたのに画面が古い

`@st.cache_data`のTTL（最大約1時間）の影響です。Streamlitプロセスを再起動してください。

### スクリーニング結果が想定より少ない

- 対象は各社の最新期末かつ`is_consolidated = 1`のみ
- 売上高がNaNの行は結果から除外
- 自己資本比率・営業利益率はページ内計算のため、分母が0や欠損の企業は条件から外れやすい

### `push.bat`で意図しないコミットメッセージになる

バッチは固定のcommitメッセージでpushします。ドキュメント追加や機能変更では使わず、通常のgit操作を使います。

```powershell
git add README.md docs
git commit -m "Document system architecture, data flow, and operations"
git push origin main
```

## データ更新手順（概要）

1. リポジトリ外で`edinet_data.sqlite3`を生成または更新
2. `data/edinet_data.sqlite3`を差し替え
3. ローカルでViewerを起動し、件数・日付範囲・代表企業を確認
4. 問題なければGitへコミット・push（ファイルサイズに注意）

このリポジトリ単体では取得の再実行はできません。

## 認証情報の管理

表示アプリに必須のSecretはありません。

注意:

- `.env`は`.gitignore`対象ですが、秘密情報をリポジトリへ置かない
- DBに個人情報や非公開データを入れない運用を前提とする
- `push.bat`やログにトークンを書かない

## 変更後の確認

アプリや`db_helper`を変更した場合:

1. `pip install -r requirements.txt`（依存追加時）
2. Streamlitを起動
3. ホーム統計が表示されること
4. Search → Company → Compare → Screening → TextBlocksを順に開く
5. DB差し替えがある場合はキャッシュクリアのため再起動

## 定期点検

データ更新のたびに、または月1回程度:

- `data/edinet_data.sqlite3`の更新日とファイルサイズ
- ホームの「データ期間」が想定どおりか
- 主要ページがエラーなく開くか
- `run.bat`のPythonパスがまだ有効か

## 既知の注意点

- このリポジトリはViewer専用で、EDINET取得・解析コードは含みません
- 同梱DBの内容（期間・件数・セクション種類）は時点依存です。ドキュメントの件数例はコード実行時点の参考値に過ぎません
- 企業詳細・テキスト閲覧の画面表示は長文を切り詰めますが、ダウンロードは全文です
- Streamlitクラウド公開URLはリポジトリに未記録です。公開したらREADMEの「公開先・起動」へ追記します
