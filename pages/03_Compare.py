# -*- coding: utf-8 -*-
"""
企業比較ページ
最大5社を選択し、主要財務指標を横並びで比較する。
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import db_helper as db

st.set_page_config(
    page_title="企業比較 | EDINET Viewer",
    page_icon="⚖️",
    layout="wide",
)

st.title("企業比較")
st.markdown("最大5社の財務データを横並びで比較できます。")

# ── 企業選択 ──────────────────────────────────────────

company_list = db.get_company_list()
if company_list.empty:
    st.warning("企業データがまだありません。")
    st.stop()

options = {
    f"{row['sec_code']} - {row['filer_name']}": row["sec_code"]
    for _, row in company_list.iterrows()
}

selected_labels = st.multiselect(
    "比較する企業を選択（最大5社）",
    list(options.keys()),
    max_selections=5,
    key="compare_companies",
)

if not selected_labels:
    st.info("企業を選択してください。")
    st.stop()

selected_codes = [options[label] for label in selected_labels]

# ── データ取得 ────────────────────────────────────────

all_fin = db.get_multi_company_financials(selected_codes)

if all_fin.empty:
    st.warning("選択した企業の財務データがまだ解析されていません。")
    st.stop()

# 連結のみフィルタ
if 1 in all_fin["is_consolidated"].values:
    all_fin = all_fin[all_fin["is_consolidated"] == 1]

# ── 最新期の比較テーブル ──────────────────────────────

st.markdown("### 最新期の比較")

# 各企業の最新期データを取得
latest_data = []
for code in selected_codes:
    company_fin = all_fin[all_fin["sec_code"] == code]
    if not company_fin.empty:
        latest = company_fin.sort_values("period_end", ascending=False).iloc[0]
        latest_data.append(latest)

if latest_data:
    compare_df = pd.DataFrame(latest_data)

    # 表示用に転置テーブルを作成
    metrics = {
        "企業名": "filer_name",
        "期末": "period_end",
        "売上高（億円）": "sales",
        "営業利益（億円）": "operating_income",
        "経常利益（億円）": "ordinary_income",
        "純利益（億円）": "net_income",
        "総資産（億円）": "total_assets",
        "純資産（億円）": "net_assets",
        "営業CF（億円）": "operating_cf",
        "投資CF（億円）": "investing_cf",
        "財務CF（億円）": "financing_cf",
    }

    rows = []
    for label, col in metrics.items():
        row = {"指標": label}
        for i, data in enumerate(latest_data):
            company_name = data.get("filer_name", f"企業{i+1}")
            val = data.get(col)
            if col == "filer_name" or col == "period_end":
                row[company_name] = val
            elif pd.notna(val):
                row[company_name] = f"{val / 1e8:,.1f}"
            else:
                row[company_name] = "-"
        rows.append(row)

    compare_display = pd.DataFrame(rows)
    st.dataframe(compare_display, hide_index=True, use_container_width=True)

# ── 推移チャート（重ね表示） ──────────────────────────

st.markdown("### 財務推移比較")

chart_metric = st.selectbox(
    "表示する指標",
    ["売上高", "営業利益", "経常利益", "純利益", "総資産", "純資産",
     "営業CF", "投資CF", "財務CF"],
    key="compare_metric",
)

metric_col_map = {
    "売上高": "sales",
    "営業利益": "operating_income",
    "経常利益": "ordinary_income",
    "純利益": "net_income",
    "総資産": "total_assets",
    "純資産": "net_assets",
    "営業CF": "operating_cf",
    "投資CF": "investing_cf",
    "財務CF": "financing_cf",
}

col_name = metric_col_map[chart_metric]

colors = ["#1a73e8", "#e53935", "#43a047", "#f9a825", "#7b1fa2"]

fig = go.Figure()

for i, code in enumerate(selected_codes):
    company_fin = all_fin[all_fin["sec_code"] == code].sort_values("period_end")
    if not company_fin.empty:
        name = company_fin.iloc[0]["filer_name"]
        values = company_fin[col_name] / 1e8  # 億円変換
        fig.add_trace(go.Scatter(
            x=company_fin["period_end"],
            y=values,
            name=f"{code} {name}",
            mode="lines+markers",
            line=dict(color=colors[i % len(colors)], width=3),
            marker=dict(size=8),
        ))

fig.update_layout(
    title=f"{chart_metric}推移比較（億円）",
    xaxis_title="期末",
    yaxis_title=f"{chart_metric}（億円）",
    height=500,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(t=80, b=40),
)

st.plotly_chart(fig, use_container_width=True)

# ── レーダーチャート ──────────────────────────────────

st.markdown("### 財務指標レーダーチャート")
st.caption("各企業の最新期データを正規化して比較します。")

if latest_data and len(latest_data) >= 2:
    radar_metrics = ["sales", "operating_income", "net_income",
                     "total_assets", "net_assets", "operating_cf"]
    radar_labels = ["売上高", "営業利益", "純利益", "総資産", "純資産", "営業CF"]

    # 正規化（各指標の最大値で割る）
    fig_radar = go.Figure()

    # 各指標の最大値を求める
    max_vals = {}
    for metric in radar_metrics:
        vals = [abs(d.get(metric, 0) or 0) for d in latest_data]
        max_vals[metric] = max(vals) if max(vals) > 0 else 1

    for i, data in enumerate(latest_data):
        name = f"{data.get('sec_code', '')} {data.get('filer_name', '')}"
        values = []
        for metric in radar_metrics:
            val = data.get(metric, 0) or 0
            normalized = val / max_vals[metric]
            values.append(normalized)
        values.append(values[0])  # 閉じる

        fig_radar.add_trace(go.Scatterpolar(
            r=values,
            theta=radar_labels + [radar_labels[0]],
            fill="toself",
            name=name,
            line=dict(color=colors[i % len(colors)]),
            opacity=0.6,
        ))

    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1.1])),
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
        margin=dict(t=40, b=80),
    )

    st.plotly_chart(fig_radar, use_container_width=True)
    st.caption("※ 各指標を選択企業間の最大値で正規化しています。マイナス値は0として表示されます。")
else:
    st.info("レーダーチャートには2社以上の選択が必要です。")
