# -*- coding: utf-8 -*-
"""
企業検索ページ
証券コード or 企業名で検索し、企業詳細ページへ遷移する。
"""

import streamlit as st
import pandas as pd
import db_helper as db

st.set_page_config(
    page_title="企業検索 | EDINET Viewer",
    page_icon="🔍",
    layout="wide",
)

st.title("企業検索")
st.markdown("証券コードまたは企業名で検索できます。")

# ── 検索フォーム ──────────────────────────────────────

col_search, col_btn = st.columns([4, 1])
with col_search:
    keyword = st.text_input(
        "検索キーワード",
        placeholder="証券コード（例: 7203）or 企業名（例: トヨタ）",
        key="search_keyword",
    )
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    search_clicked = st.button("検索", type="primary", use_container_width=True)

# ── 検索結果 ──────────────────────────────────────────

if keyword or search_clicked:
    if keyword.strip():
        results = db.search_companies(keyword)

        if not results.empty:
            st.success(f"{len(results)} 件の企業が見つかりました")

            # 表示用に整形
            display_df = results.rename(columns={
                "sec_code": "証券コード",
                "filer_name": "企業名",
                "doc_count": "書類数",
                "latest_date": "最終提出日",
            })

            # 各行にリンクを追加
            for _, row in results.iterrows():
                sec = row["sec_code"]
                name = row["filer_name"]
                count = row["doc_count"]
                latest = row["latest_date"]

                col1, col2, col3, col4 = st.columns([1, 3, 1, 2])
                with col1:
                    st.code(sec)
                with col2:
                    st.markdown(f"**{name}**")
                with col3:
                    st.caption(f"{count} 件")
                with col4:
                    cols = st.columns(3)
                    with cols[0]:
                        st.link_button(
                            "詳細",
                            f"/Company?sec_code={sec}",
                            use_container_width=True,
                        )
                    with cols[1]:
                        st.link_button(
                            "テキスト",
                            f"/TextBlocks?sec_code={sec}",
                            use_container_width=True,
                        )
                st.divider()
        else:
            st.warning("該当する企業が見つかりませんでした。")
    else:
        st.info("キーワードを入力してください。")

# ── 全企業一覧 ────────────────────────────────────────

with st.expander("全企業一覧を表示", expanded=False):
    all_companies = db.get_company_list()
    if not all_companies.empty:
        st.caption(f"全 {len(all_companies)} 企業")

        # ページネーション
        page_size = 50
        total_pages = max(1, (len(all_companies) - 1) // page_size + 1)
        page = st.number_input(
            "ページ", min_value=1, max_value=total_pages, value=1, key="company_page"
        )
        start = (page - 1) * page_size
        end = start + page_size

        page_df = all_companies.iloc[start:end]
        display_df = page_df.rename(columns={
            "sec_code": "証券コード",
            "filer_name": "企業名",
            "doc_count": "書類数",
            "latest_date": "最終提出日",
        })

        st.dataframe(
            display_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "証券コード": st.column_config.TextColumn(width="small"),
                "書類数": st.column_config.NumberColumn(width="small"),
            },
        )

        st.caption(f"ページ {page} / {total_pages}")
    else:
        st.info("企業データがまだありません。")
