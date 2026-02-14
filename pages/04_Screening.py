# -*- coding: utf-8 -*-
"""
スクリーニングページ
売上高・利益・自己資本比率等の条件で企業を絞り込む。
"""

import streamlit as st
import pandas as pd
import db_helper as db

st.set_page_config(
    page_title="スクリーニング | EDINET Viewer",
    page_icon="🎯",
    layout="wide",
)

st.title("スクリーニング")
st.markdown("財務指標の条件で企業を絞り込みます。各企業の最新期データが対象です。")

# ── データ取得 ────────────────────────────────────────

screening_data = db.get_screening_data()

if screening_data.empty:
    st.warning("スクリーニング用の財務データがまだありません。")
    st.stop()

# 億円変換した列を追加
yen_cols = ["sales", "operating_income", "ordinary_income", "net_income",
            "total_assets", "net_assets",
            "operating_cf", "investing_cf", "financing_cf"]
for col in yen_cols:
    if col in screening_data.columns:
        screening_data[f"{col}_oku"] = screening_data[col] / 1e8

# 自己資本比率 = 純資産 / 総資産 * 100
screening_data["equity_ratio"] = (
    screening_data["net_assets"] / screening_data["total_assets"] * 100
).round(1)

# 営業利益率 = 営業利益 / 売上高 * 100
screening_data["op_margin"] = (
    screening_data["operating_income"] / screening_data["sales"] * 100
).round(1)

st.caption(f"対象企業数: {len(screening_data):,} 社")

# ── フィルタ条件 ──────────────────────────────────────

st.markdown("### フィルタ条件")
st.caption("億円単位で入力してください。条件を設定しないフィールドは空のままにしてください。")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**売上高（億円）**")
    sales_min = st.number_input("最小", value=None, key="sales_min",
                                 placeholder="例: 100", step=10.0)
    sales_max = st.number_input("最大", value=None, key="sales_max",
                                 placeholder="例: 10000", step=10.0)

    st.markdown("**営業利益（億円）**")
    op_min = st.number_input("最小", value=None, key="op_min",
                              placeholder="例: 10", step=1.0)
    op_max = st.number_input("最大", value=None, key="op_max",
                              placeholder="例: 1000", step=1.0)

with col2:
    st.markdown("**純利益（億円）**")
    ni_min = st.number_input("最小", value=None, key="ni_min",
                              placeholder="例: 5", step=1.0)
    ni_max = st.number_input("最大", value=None, key="ni_max",
                              placeholder="例: 500", step=1.0)

    st.markdown("**自己資本比率（%）**")
    eq_min = st.number_input("最小", value=None, key="eq_min",
                              placeholder="例: 30", step=1.0)
    eq_max = st.number_input("最大", value=None, key="eq_max",
                              placeholder="例: 80", step=1.0)

with col3:
    st.markdown("**営業利益率（%）**")
    margin_min = st.number_input("最小", value=None, key="margin_min",
                                  placeholder="例: 5", step=0.5)
    margin_max = st.number_input("最大", value=None, key="margin_max",
                                  placeholder="例: 30", step=0.5)

    st.markdown("**総資産（億円）**")
    ta_min = st.number_input("最小", value=None, key="ta_min",
                              placeholder="例: 100", step=10.0)
    ta_max = st.number_input("最大", value=None, key="ta_max",
                              placeholder="例: 50000", step=10.0)

# ── フィルタ適用 ──────────────────────────────────────

filtered = screening_data.copy()

# 売上高
if sales_min is not None:
    filtered = filtered[filtered["sales_oku"] >= sales_min]
if sales_max is not None:
    filtered = filtered[filtered["sales_oku"] <= sales_max]

# 営業利益
if op_min is not None:
    filtered = filtered[filtered["operating_income_oku"] >= op_min]
if op_max is not None:
    filtered = filtered[filtered["operating_income_oku"] <= op_max]

# 純利益
if ni_min is not None:
    filtered = filtered[filtered["net_income_oku"] >= ni_min]
if ni_max is not None:
    filtered = filtered[filtered["net_income_oku"] <= ni_max]

# 自己資本比率
if eq_min is not None:
    filtered = filtered[filtered["equity_ratio"] >= eq_min]
if eq_max is not None:
    filtered = filtered[filtered["equity_ratio"] <= eq_max]

# 営業利益率
if margin_min is not None:
    filtered = filtered[filtered["op_margin"] >= margin_min]
if margin_max is not None:
    filtered = filtered[filtered["op_margin"] <= margin_max]

# 総資産
if ta_min is not None:
    filtered = filtered[filtered["total_assets_oku"] >= ta_min]
if ta_max is not None:
    filtered = filtered[filtered["total_assets_oku"] <= ta_max]

# NaN を除外（フィルタ対象の指標が存在しない企業）
filtered = filtered.dropna(subset=["sales"])

# ── 結果表示 ──────────────────────────────────────────

st.divider()
st.markdown(f"### 検索結果: **{len(filtered):,}** 社")

if not filtered.empty:
    # ソート
    sort_col = st.selectbox(
        "並び替え",
        ["売上高（降順）", "営業利益（降順）", "純利益（降順）",
         "自己資本比率（降順）", "営業利益率（降順）", "総資産（降順）"],
        key="sort_option",
    )

    sort_map = {
        "売上高（降順）": ("sales_oku", False),
        "営業利益（降順）": ("operating_income_oku", False),
        "純利益（降順）": ("net_income_oku", False),
        "自己資本比率（降順）": ("equity_ratio", False),
        "営業利益率（降順）": ("op_margin", False),
        "総資産（降順）": ("total_assets_oku", False),
    }

    sort_key, sort_asc = sort_map.get(sort_col, ("sales_oku", False))
    filtered = filtered.sort_values(sort_key, ascending=sort_asc, na_position="last")

    # 表示用 DataFrame
    display = filtered[[
        "sec_code", "filer_name", "period_end",
        "sales_oku", "operating_income_oku", "net_income_oku",
        "total_assets_oku", "net_assets_oku",
        "equity_ratio", "op_margin",
    ]].rename(columns={
        "sec_code": "コード",
        "filer_name": "企業名",
        "period_end": "期末",
        "sales_oku": "売上高(億円)",
        "operating_income_oku": "営業利益(億円)",
        "net_income_oku": "純利益(億円)",
        "total_assets_oku": "総資産(億円)",
        "net_assets_oku": "純資産(億円)",
        "equity_ratio": "自己資本比率(%)",
        "op_margin": "営業利益率(%)",
    })

    # 小数点整形
    for col in ["売上高(億円)", "営業利益(億円)", "純利益(億円)",
                "総資産(億円)", "純資産(億円)"]:
        if col in display.columns:
            display[col] = display[col].round(1)

    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=min(len(display) * 35 + 40, 600),
        column_config={
            "コード": st.column_config.TextColumn(width="small"),
            "期末": st.column_config.TextColumn(width="small"),
        },
    )

    # CSV ダウンロード
    csv = display.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "CSV ダウンロード",
        csv,
        file_name="screening_result.csv",
        mime="text/csv",
    )
else:
    st.info("条件に合致する企業がありません。条件を緩和してみてください。")
