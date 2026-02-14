# -*- coding: utf-8 -*-
"""
企業詳細ページ
URLパラメータ ?sec_code=XXXXX で企業を指定し、
財務テーブル・チャート・テキストブロックを表示する。
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import db_helper as db

st.set_page_config(
    page_title="企業詳細 | EDINET Viewer",
    page_icon="🏢",
    layout="wide",
)

# ── 企業選択 ──────────────────────────────────────────

# URLパラメータから取得
params = st.query_params
sec_code_param = params.get("sec_code", "")

# 企業選択 UI
st.title("企業詳細")

company_list = db.get_company_list()
if company_list.empty:
    st.warning("企業データがまだありません。")
    st.stop()

# 選択肢を作成
options = {
    f"{row['sec_code']} - {row['filer_name']}": row["sec_code"]
    for _, row in company_list.iterrows()
}

# デフォルト選択
default_idx = 0
if sec_code_param:
    for i, (label, code) in enumerate(options.items()):
        if code == sec_code_param:
            default_idx = i
            break

selected_label = st.selectbox(
    "企業を選択",
    list(options.keys()),
    index=default_idx,
    key="company_select",
)
sec_code = options[selected_label]

# ── 企業情報ヘッダー ──────────────────────────────────

info = db.get_company_info(sec_code)
if not info:
    st.error("企業情報が見つかりません。")
    st.stop()

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    st.markdown(f"## {info.get('filer_name', '')}  ({sec_code})")
with col2:
    st.metric("書類数", f"{info.get('doc_count', 0):,}")
with col3:
    st.metric("最終提出日", info.get("latest_date", "-"))

st.divider()

# ── タブ構成 ──────────────────────────────────────────

tab_fin, tab_chart, tab_text, tab_docs = st.tabs([
    "📊 財務データ", "📈 チャート", "📝 テキスト", "📄 書類一覧"
])

# ── 財務データタブ ────────────────────────────────────

with tab_fin:
    st.markdown("### 主要財務指標")

    key_fin = db.get_key_financials(sec_code)

    if not key_fin.empty:
        # 連結/単体の選択
        consol_options = key_fin["is_consolidated"].unique()
        consol_labels = {1: "連結", 0: "単体"}
        if len(consol_options) > 1:
            consol = st.radio(
                "連結 / 単体",
                consol_options,
                format_func=lambda x: consol_labels.get(x, str(x)),
                horizontal=True,
                key="fin_consol",
            )
            fin_df = key_fin[key_fin["is_consolidated"] == consol].copy()
        else:
            fin_df = key_fin.copy()

        # 表示用に整形（金額を億円に変換）
        display = fin_df[["period_end", "sales", "operating_income",
                          "ordinary_income", "net_income",
                          "total_assets", "net_assets",
                          "operating_cf", "investing_cf", "financing_cf"]].copy()

        # 億円変換
        yen_cols = ["sales", "operating_income", "ordinary_income", "net_income",
                    "total_assets", "net_assets",
                    "operating_cf", "investing_cf", "financing_cf"]
        for col in yen_cols:
            if col in display.columns:
                display[col] = display[col].apply(
                    lambda x: round(x / 1e8, 1) if pd.notna(x) else None
                )

        display = display.rename(columns={
            "period_end": "期末",
            "sales": "売上高(億円)",
            "operating_income": "営業利益(億円)",
            "ordinary_income": "経常利益(億円)",
            "net_income": "純利益(億円)",
            "total_assets": "総資産(億円)",
            "net_assets": "純資産(億円)",
            "operating_cf": "営業CF(億円)",
            "investing_cf": "投資CF(億円)",
            "financing_cf": "財務CF(億円)",
        })

        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "期末": st.column_config.TextColumn(width="small"),
            },
        )

        # CSV ダウンロード
        csv = display.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "CSV ダウンロード",
            csv,
            file_name=f"{sec_code}_financials.csv",
            mime="text/csv",
        )
    else:
        st.info("この企業の財務データはまだ解析されていません。")

# ── チャートタブ ──────────────────────────────────────

with tab_chart:
    st.markdown("### 財務推移チャート")

    key_fin = db.get_key_financials(sec_code)

    if not key_fin.empty:
        # 連結のみでフィルタ（存在すれば）
        if 1 in key_fin["is_consolidated"].values:
            chart_df = key_fin[key_fin["is_consolidated"] == 1].copy()
        else:
            chart_df = key_fin.copy()

        chart_df = chart_df.sort_values("period_end")

        # 億円変換
        for col in ["sales", "operating_income", "ordinary_income", "net_income",
                     "total_assets", "net_assets",
                     "operating_cf", "investing_cf", "financing_cf"]:
            if col in chart_df.columns:
                chart_df[col] = chart_df[col] / 1e8

        # ── 売上・利益チャート ──
        fig1 = make_subplots(specs=[[{"secondary_y": True}]])

        fig1.add_trace(
            go.Bar(
                x=chart_df["period_end"], y=chart_df["sales"],
                name="売上高", marker_color="#1a73e8", opacity=0.7,
            ),
            secondary_y=False,
        )
        fig1.add_trace(
            go.Scatter(
                x=chart_df["period_end"], y=chart_df["operating_income"],
                name="営業利益", line=dict(color="#e53935", width=3),
                mode="lines+markers",
            ),
            secondary_y=True,
        )
        fig1.add_trace(
            go.Scatter(
                x=chart_df["period_end"], y=chart_df["net_income"],
                name="純利益", line=dict(color="#43a047", width=3),
                mode="lines+markers",
            ),
            secondary_y=True,
        )

        fig1.update_layout(
            title="売上高・利益推移（億円）",
            height=450,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(t=80, b=40),
        )
        fig1.update_yaxes(title_text="売上高（億円）", secondary_y=False)
        fig1.update_yaxes(title_text="利益（億円）", secondary_y=True)

        st.plotly_chart(fig1, use_container_width=True)

        # ── BS チャート ──
        col_bs1, col_bs2 = st.columns(2)

        with col_bs1:
            fig2 = go.Figure()
            fig2.add_trace(go.Bar(
                x=chart_df["period_end"], y=chart_df["total_assets"],
                name="総資産", marker_color="#1565c0",
            ))
            fig2.add_trace(go.Bar(
                x=chart_df["period_end"], y=chart_df["net_assets"],
                name="純資産", marker_color="#2e7d32",
            ))
            fig2.update_layout(
                title="総資産・純資産推移（億円）",
                barmode="group",
                height=350,
                margin=dict(t=60, b=40),
            )
            st.plotly_chart(fig2, use_container_width=True)

        # ── CF チャート ──
        with col_bs2:
            fig3 = go.Figure()
            fig3.add_trace(go.Bar(
                x=chart_df["period_end"], y=chart_df["operating_cf"],
                name="営業CF", marker_color="#1a73e8",
            ))
            fig3.add_trace(go.Bar(
                x=chart_df["period_end"], y=chart_df["investing_cf"],
                name="投資CF", marker_color="#e53935",
            ))
            fig3.add_trace(go.Bar(
                x=chart_df["period_end"], y=chart_df["financing_cf"],
                name="財務CF", marker_color="#f9a825",
            ))
            fig3.update_layout(
                title="キャッシュフロー推移（億円）",
                barmode="group",
                height=350,
                margin=dict(t=60, b=40),
            )
            st.plotly_chart(fig3, use_container_width=True)

    else:
        st.info("チャート表示にはデータの解析が必要です。")

# ── テキストブロックタブ ──────────────────────────────

with tab_text:
    st.markdown("### テキストブロック（事業の状況等）")

    text_blocks = db.get_company_text_blocks(sec_code)

    if not text_blocks.empty:
        # 期で選択
        periods = sorted(text_blocks["period_end"].unique(), reverse=True)
        selected_period = st.selectbox(
            "期末を選択",
            periods,
            key="text_period",
        )

        period_blocks = text_blocks[text_blocks["period_end"] == selected_period]

        if not period_blocks.empty:
            st.caption(f"{len(period_blocks)} 件のテキストブロック")

            for _, block in period_blocks.iterrows():
                section = block["section_label"] or block["element_name"]
                content = block["text_content"] or ""

                with st.expander(f"**{section}**", expanded=False):
                    if content:
                        # 長いテキストは折り返し表示
                        st.markdown(
                            f'<div style="white-space: pre-wrap; '
                            f'font-size: 0.9em; line-height: 1.6; '
                            f'max-height: 500px; overflow-y: auto; '
                            f'padding: 10px; background: #fafafa; '
                            f'border-radius: 8px;">{content[:10000]}</div>',
                            unsafe_allow_html=True,
                        )
                        if len(content) > 10000:
                            st.caption(f"（テキスト全長: {len(content):,} 文字、先頭10,000文字を表示）")
                    else:
                        st.caption("テキストなし")
        else:
            st.info("この期のテキストブロックはありません。")
    else:
        st.info("この企業のテキストブロックはまだ抽出されていません。")

# ── 書類一覧タブ ──────────────────────────────────────

with tab_docs:
    st.markdown("### 提出書類一覧")

    docs = db.get_company_documents(sec_code)

    if not docs.empty:
        docs["書類種別"] = docs["doc_type_code"].map(
            lambda x: db.DOC_TYPE_NAMES.get(x, x)
        )

        display_docs = docs[[
            "file_date", "書類種別", "doc_description",
            "period_start", "period_end",
        ]].rename(columns={
            "file_date": "提出日",
            "doc_description": "概要",
            "period_start": "期首",
            "period_end": "期末",
        })

        st.dataframe(
            display_docs,
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.info("書類データがありません。")
