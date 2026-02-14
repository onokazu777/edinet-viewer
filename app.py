# -*- coding: utf-8 -*-
"""
EDINET Financial Viewer — ダッシュボード

蓄積した EDINET 財務データを閲覧・検索・比較する Streamlit アプリ。
"""

import streamlit as st
import pandas as pd
import db_helper as db

# ── ページ設定 ────────────────────────────────────────

st.set_page_config(
    page_title="EDINET Financial Viewer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── カスタム CSS ──────────────────────────────────────

st.markdown("""
<style>
    .metric-card {
        background: #f8f9fa;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        border: 1px solid #e9ecef;
    }
    .metric-card .value {
        font-size: 2.2em;
        font-weight: 700;
        color: #1a73e8;
        line-height: 1.2;
    }
    .metric-card .label {
        font-size: 0.9em;
        color: #666;
        margin-top: 4px;
    }
    .doc-type-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.8em;
        font-weight: 600;
        color: #fff;
    }
    .badge-120 { background: #1976d2; }
    .badge-130 { background: #64b5f6; }
    .badge-140 { background: #7b1fa2; }
    .badge-150 { background: #ce93d8; }
    .badge-160 { background: #2e7d32; }
    .badge-170 { background: #81c784; }
    .badge-060 { background: #ef6c00; }
    .badge-070 { background: #ffb74d; }
    a { text-decoration: none; }
</style>
""", unsafe_allow_html=True)

# ── サイドバー ────────────────────────────────────────

with st.sidebar:
    st.title("EDINET Viewer")
    st.caption("有価証券報告書・財務データビューア")
    st.divider()
    st.markdown("### クイック検索")
    quick_search = st.text_input(
        "証券コード or 企業名",
        placeholder="例: 7203, トヨタ",
        key="sidebar_search",
    )
    if quick_search:
        results = db.search_companies(quick_search)
        if not results.empty:
            for _, row in results.head(10).iterrows():
                sec = row["sec_code"]
                name = row["filer_name"]
                st.markdown(
                    f"[{sec} {name}](/Company?sec_code={sec})"
                )
        else:
            st.info("該当企業が見つかりません")

# ── メインコンテンツ ──────────────────────────────────

st.title("EDINET Financial Viewer")
st.markdown("有価証券報告書・半期報告書から抽出した財務データを閲覧・検索・比較")

# 統計情報
try:
    stats = db.get_db_stats()
except Exception as e:
    st.error(f"データベース接続エラー: {e}")
    st.info("data/edinet_data.sqlite3 を配置してください。")
    st.stop()

# メトリクスカード
st.markdown("### データ概要")
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("登録企業数", f"{stats['total_companies']:,}")
with col2:
    st.metric("書類数", f"{stats['total_docs']:,}")
with col3:
    st.metric("解析済み", f"{stats['parsed_docs']:,}")
with col4:
    st.metric("財務レコード", f"{stats['financial_records']:,}")
with col5:
    st.metric("テキストブロック", f"{stats['text_blocks']:,}")

if stats["date_from"] and stats["date_to"]:
    st.caption(f"データ期間: {stats['date_from']} ～ {stats['date_to']}")

# ── 書類種別の内訳 ────────────────────────────────────

st.markdown("### 書類種別の内訳")
doc_types = stats.get("doc_type_counts", {})
if doc_types:
    type_data = []
    for code, count in doc_types.items():
        name = db.DOC_TYPE_NAMES.get(code, f"その他({code})")
        type_data.append({"書類種別": name, "コード": code, "件数": count})
    df_types = pd.DataFrame(type_data)
    col_chart, col_table = st.columns([2, 1])
    with col_chart:
        st.bar_chart(df_types.set_index("書類種別")["件数"])
    with col_table:
        st.dataframe(df_types, hide_index=True, use_container_width=True)

# ── 最近の提出書類 ────────────────────────────────────

st.markdown("### 最近の提出書類")
recent = db.get_recent_documents(limit=30)

if not recent.empty:
    # 書類種別名を追加
    recent["書類種別"] = recent["doc_type_code"].map(
        lambda x: db.DOC_TYPE_NAMES.get(x, x)
    )
    # 表示用に整形
    display_cols = {
        "file_date": "提出日",
        "sec_code": "コード",
        "filer_name": "企業名",
        "書類種別": "書類種別",
        "doc_description": "概要",
        "period_end": "期末",
    }
    df_display = recent[list(display_cols.keys())].rename(columns=display_cols)
    st.dataframe(
        df_display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "コード": st.column_config.TextColumn(width="small"),
            "提出日": st.column_config.TextColumn(width="small"),
            "期末": st.column_config.TextColumn(width="small"),
        },
    )
else:
    st.info("データがまだありません。")

# ── フッター ──────────────────────────────────────────

st.divider()
st.caption(
    "データ出典: [EDINET](https://disclosure2.edinet-fsa.go.jp/) "
    "（金融庁 電子開示システム）"
)
