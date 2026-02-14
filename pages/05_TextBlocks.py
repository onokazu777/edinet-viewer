# -*- coding: utf-8 -*-
"""
テキストブロック閲覧ページ
事業の状況、リスク、MD&A 等のテキストを閲覧・検索する。
"""

import re
import streamlit as st
import pandas as pd
import db_helper as db

st.set_page_config(
    page_title="テキスト閲覧 | EDINET Viewer",
    page_icon="📝",
    layout="wide",
)

st.title("テキストブロック閲覧")
st.markdown("有価証券報告書の「事業の状況」「事業等のリスク」等のテキスト情報を検索・閲覧できます。")

# ── フィルタ ──────────────────────────────────────────

col1, col2, col3 = st.columns(3)

with col1:
    # URLパラメータから企業コードを取得
    params = st.query_params
    default_code = params.get("sec_code", "")

    sec_code_input = st.text_input(
        "証券コード",
        value=default_code,
        placeholder="例: 7203",
        key="text_sec_code",
    )

with col2:
    # セクション選択
    try:
        sections = db.get_text_block_sections()
    except Exception:
        sections = []

    section_options = ["（すべて）"] + sections
    selected_section = st.selectbox(
        "セクション",
        section_options,
        key="text_section",
    )

with col3:
    keyword = st.text_input(
        "キーワード検索",
        placeholder="テキスト内のキーワード",
        key="text_keyword",
    )

# 件数制限
limit = st.slider("最大表示件数", 10, 200, 50, step=10, key="text_limit")

# ── 検索実行 ──────────────────────────────────────────

search_params = {}
if sec_code_input.strip():
    search_params["sec_code"] = sec_code_input.strip()
if selected_section != "（すべて）":
    search_params["section_label"] = selected_section
if keyword.strip():
    search_params["keyword"] = keyword.strip()

results = db.search_text_blocks(**search_params, limit=limit)

# ── 結果表示 ──────────────────────────────────────────

st.divider()

if results.empty:
    if not search_params:
        st.info("フィルタ条件を設定して検索してください。")
    else:
        st.warning("条件に合致するテキストブロックが見つかりませんでした。")
    st.stop()

st.markdown(f"### 検索結果: **{len(results)}** 件")

# 結果の概要テーブル
summary = results[[
    "sec_code", "filer_name", "period_end", "section_label"
]].rename(columns={
    "sec_code": "コード",
    "filer_name": "企業名",
    "period_end": "期末",
    "section_label": "セクション",
})

with st.expander("結果一覧（テーブル）", expanded=False):
    st.dataframe(summary, hide_index=True, use_container_width=True)

# ── 各テキストブロックを表示 ──────────────────────────

for idx, (_, block) in enumerate(results.iterrows()):
    sec = block["sec_code"]
    name = block["filer_name"]
    period = block["period_end"]
    section = block["section_label"] or block["element_name"]
    content = block["text_content"] or ""

    header = f"{sec} {name} | {period} | {section}"

    with st.expander(header, expanded=(idx == 0)):
        if content:
            # キーワードハイライト
            display_text = content
            if keyword.strip():
                # HTML エスケープしてからハイライト
                escaped_keyword = re.escape(keyword.strip())
                display_text = re.sub(
                    f"({escaped_keyword})",
                    r'<mark style="background-color: #fff176; padding: 1px 3px; '
                    r'border-radius: 3px;">\1</mark>',
                    display_text,
                    flags=re.IGNORECASE,
                )

            st.markdown(
                f'<div style="white-space: pre-wrap; font-size: 0.9em; '
                f'line-height: 1.7; max-height: 600px; overflow-y: auto; '
                f'padding: 15px; background: #fafafa; border-radius: 8px; '
                f'border: 1px solid #e9ecef;">'
                f'{display_text[:15000]}</div>',
                unsafe_allow_html=True,
            )

            # テキスト統計
            char_count = len(content)
            st.caption(f"文字数: {char_count:,}")

            if char_count > 15000:
                st.caption("（先頭 15,000 文字を表示）")

            # 個別ダウンロード
            st.download_button(
                "テキストをダウンロード",
                content.encode("utf-8"),
                file_name=f"{sec}_{period}_{section}.txt",
                mime="text/plain",
                key=f"dl_{idx}",
            )
        else:
            st.caption("テキストなし")

# ── 一括ダウンロード ──────────────────────────────────

st.divider()

if not results.empty:
    st.markdown("### 一括ダウンロード")

    # CSV 形式
    csv_data = results[[
        "sec_code", "filer_name", "period_start", "period_end",
        "section_label", "text_content",
    ]].rename(columns={
        "sec_code": "証券コード",
        "filer_name": "企業名",
        "period_start": "期首",
        "period_end": "期末",
        "section_label": "セクション",
        "text_content": "テキスト",
    })

    csv = csv_data.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "検索結果を CSV でダウンロード",
        csv,
        file_name="text_blocks_search_result.csv",
        mime="text/csv",
        key="bulk_csv",
    )
