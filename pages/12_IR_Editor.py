# -*- coding: utf-8 -*-
"""
Insight Arc — F-02/F-04/F-06 データ分析・グラフ同期エディタ

Excel データとグラフの動的連動、5年トレンド分析、
スケーリング表示を行うページ。
"""

import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import auth_helper as auth
import ir_db_helper as ir_db
import db_helper as db
from ai_mock import MockAIEngine

st.set_page_config(
    page_title="データ分析・エディタ | Insight Arc",
    page_icon="📈",
    layout="wide",
)

# ── 初期化 ───────────────────────────────────────────
ir_db.init_ir_tables()
user = auth.require_login()
user_id = user["user_id"]
ai = MockAIEngine()

# ── グラフ高さ制約（仕様: 配置固定）──────────────────
CHART_HEIGHT_MAIN = 450
CHART_HEIGHT_SUB = 350

# ── プロジェクト選択 ──────────────────────────────────
params = st.query_params
project_id_param = params.get("project_id", "")

projects = ir_db.get_user_projects(user_id)
if projects.empty:
    st.warning("先にプロジェクトを作成してください。")
    st.link_button("ダッシュボードへ", "/IR_Dashboard")
    st.stop()

project_options = {
    f"{row['project_id']}: {row['title']}": row["project_id"]
    for _, row in projects.iterrows()
}

default_idx = 0
if project_id_param:
    for i, (_, pid) in enumerate(project_options.items()):
        if str(pid) == str(project_id_param):
            default_idx = i
            break

selected_label = st.selectbox(
    "プロジェクトを選択", list(project_options.keys()),
    index=default_idx, key="editor_project",
)
project_id = project_options[selected_label]
project = ir_db.get_project(project_id)

st.title(f"データ分析・グラフ同期 — {project['title']}")

# ── データソース選択 ──────────────────────────────────

st.markdown("### データソース")

tab_excel, tab_edinet = st.tabs(["📁 アップロードExcel", "📊 EDINET データ"])

# データを保持するためのセッション変数
analysis_df = pd.DataFrame()

# ── タブ1: アップロードExcelデータ ────────────────────

with tab_excel:
    st.caption("F-02: Excel内の業績/KPI数値とグラフを動的に連動します。")

    excel_data = ir_db.get_project_excel_data(project_id)

    if excel_data.empty:
        st.info("Excelデータがありません。先にファイルをアップロードしてください。")
        st.link_button("アップロードページへ", f"/IR_Upload?project_id={project_id}")
    else:
        # データセット選択
        data_options = {
            f"{row['label']} (ID:{row['data_id']})": row["data_id"]
            for _, row in excel_data.iterrows()
        }
        selected_data = st.selectbox(
            "データセットを選択",
            list(data_options.keys()),
            key="excel_data_select",
        )
        data_id = data_options[selected_data]

        # データ読み込み
        row = excel_data[excel_data["data_id"] == data_id].iloc[0]
        try:
            records = json.loads(row["data_json"])
            df = pd.DataFrame(records)

            # データプレビュー
            st.markdown("#### データプレビュー")
            st.dataframe(df, use_container_width=True, height=200)

            # グラフ生成用にデータを保持
            analysis_df = df

        except Exception as e:
            st.error(f"データの読み込みに失敗しました: {e}")

# ── タブ2: EDINETデータ ──────────────────────────────

with tab_edinet:
    st.caption("EDINETから取得した財務データを利用してグラフを生成します。")

    sec_code = project.get("sec_code", "")
    if not sec_code:
        sec_code = st.text_input("証券コードを入力", placeholder="例: 7203", key="edinet_sec")

    if sec_code:
        edinet_fin = db.get_key_financials(sec_code)

        if not edinet_fin.empty:
            # 連結のみフィルタ
            if 1 in edinet_fin["is_consolidated"].values:
                edinet_fin = edinet_fin[edinet_fin["is_consolidated"] == 1]

            edinet_fin = edinet_fin.sort_values("period_end")

            # F-04: 直近5年間（20四半期）に制限
            if len(edinet_fin) > 20:
                edinet_fin = edinet_fin.tail(20)

            # 億円変換
            yen_cols = ["sales", "operating_income", "ordinary_income", "net_income",
                        "total_assets", "net_assets",
                        "operating_cf", "investing_cf", "financing_cf"]
            for col in yen_cols:
                if col in edinet_fin.columns:
                    edinet_fin[col] = edinet_fin[col] / 1e8

            st.markdown(f"#### {sec_code} の財務データ（直近5年間）")
            st.dataframe(
                edinet_fin[["period_end"] + [c for c in yen_cols if c in edinet_fin.columns]].rename(
                    columns={
                        "period_end": "期末", "sales": "売上高(億円)",
                        "operating_income": "営業利益(億円)", "ordinary_income": "経常利益(億円)",
                        "net_income": "純利益(億円)", "total_assets": "総資産(億円)",
                        "net_assets": "純資産(億円)", "operating_cf": "営業CF(億円)",
                        "investing_cf": "投資CF(億円)", "financing_cf": "財務CF(億円)",
                    }
                ),
                use_container_width=True,
                height=250,
            )

            analysis_df = edinet_fin
        else:
            st.warning(f"証券コード {sec_code} のデータが見つかりません。")
    else:
        st.info("証券コードを入力するか、プロジェクトに証券コードを設定してください。")

# ── F-02/F-06: グラフ生成＆同期 ──────────────────────

st.divider()
st.markdown("### グラフ生成・同期")
st.caption("F-02: Excelデータと連動 / F-06: 5年スケーリング表示（グラフ高さ固定）")

if not analysis_df.empty:
    # 数値列を自動検出
    numeric_cols = analysis_df.select_dtypes(include="number").columns.tolist()
    date_cols = [c for c in analysis_df.columns if any(
        kw in str(c).lower() for kw in ["date", "period", "期", "年", "月"]
    )]

    if not date_cols:
        # 最初の非数値列をX軸候補に
        non_numeric = [c for c in analysis_df.columns if c not in numeric_cols]
        date_cols = non_numeric[:1] if non_numeric else []

    x_axis = st.selectbox(
        "X軸（期間）",
        analysis_df.columns.tolist(),
        index=analysis_df.columns.tolist().index(date_cols[0]) if date_cols else 0,
        key="x_axis_select",
    )

    # グラフ種類選択
    chart_type = st.radio(
        "グラフタイプ",
        ["売上・利益推移", "BS推移", "CF推移", "カスタム"],
        horizontal=True,
        key="chart_type",
    )

    # ── 売上・利益推移チャート ──
    if chart_type == "売上・利益推移":
        sales_col = st.selectbox(
            "売上高の列", numeric_cols,
            index=next((i for i, c in enumerate(numeric_cols) if "sales" in c.lower() or "売上" in c), 0),
            key="sales_col",
        )
        profit_cols = st.multiselect(
            "利益の列（複数選択可）", numeric_cols,
            default=[c for c in numeric_cols if any(
                kw in c.lower() for kw in ["operating", "net", "営業", "純"]
            )][:2],
            key="profit_cols",
        )

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        # F-06: 高さ制限を維持したスケーリング
        fig.add_trace(
            go.Bar(
                x=analysis_df[x_axis], y=analysis_df[sales_col],
                name=sales_col, marker_color="#1a73e8", opacity=0.7,
            ),
            secondary_y=False,
        )

        colors = ["#e53935", "#43a047", "#f9a825", "#7b1fa2"]
        for i, col in enumerate(profit_cols):
            fig.add_trace(
                go.Scatter(
                    x=analysis_df[x_axis], y=analysis_df[col],
                    name=col, mode="lines+markers",
                    line=dict(color=colors[i % len(colors)], width=3),
                ),
                secondary_y=True,
            )

        fig.update_layout(
            title="売上高・利益推移",
            height=CHART_HEIGHT_MAIN,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(t=80, b=40),
        )
        fig.update_yaxes(title_text=sales_col, secondary_y=False)
        fig.update_yaxes(title_text="利益", secondary_y=True)

        st.plotly_chart(fig, use_container_width=True)

    # ── BS推移チャート ──
    elif chart_type == "BS推移":
        bs_cols = st.multiselect(
            "BS項目を選択",
            numeric_cols,
            default=[c for c in numeric_cols if any(
                kw in c.lower() for kw in ["assets", "資産", "純資産"]
            )][:2],
            key="bs_cols",
        )

        if bs_cols:
            fig = go.Figure()
            colors = ["#1565c0", "#2e7d32", "#f9a825", "#7b1fa2"]
            for i, col in enumerate(bs_cols):
                fig.add_trace(go.Bar(
                    x=analysis_df[x_axis], y=analysis_df[col],
                    name=col, marker_color=colors[i % len(colors)],
                ))
            fig.update_layout(
                title="BS推移",
                barmode="group",
                height=CHART_HEIGHT_SUB,
                margin=dict(t=60, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── CF推移チャート ──
    elif chart_type == "CF推移":
        cf_cols = st.multiselect(
            "CF項目を選択",
            numeric_cols,
            default=[c for c in numeric_cols if any(
                kw in c.lower() for kw in ["cf", "キャッシュ", "cash"]
            )][:3],
            key="cf_cols",
        )

        if cf_cols:
            fig = go.Figure()
            colors = ["#1a73e8", "#e53935", "#f9a825"]
            for i, col in enumerate(cf_cols):
                fig.add_trace(go.Bar(
                    x=analysis_df[x_axis], y=analysis_df[col],
                    name=col, marker_color=colors[i % len(colors)],
                ))
            fig.update_layout(
                title="キャッシュフロー推移",
                barmode="group",
                height=CHART_HEIGHT_SUB,
                margin=dict(t=60, b=40),
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── カスタムチャート ──
    elif chart_type == "カスタム":
        y_cols = st.multiselect(
            "Y軸の列を選択（複数可）",
            numeric_cols,
            key="custom_y_cols",
        )

        custom_chart_style = st.radio(
            "チャートスタイル",
            ["折れ線", "棒グラフ", "エリア"],
            horizontal=True,
            key="custom_style",
        )

        if y_cols:
            fig = go.Figure()
            colors = ["#1a73e8", "#e53935", "#43a047", "#f9a825", "#7b1fa2"]
            for i, col in enumerate(y_cols):
                if custom_chart_style == "折れ線":
                    fig.add_trace(go.Scatter(
                        x=analysis_df[x_axis], y=analysis_df[col],
                        name=col, mode="lines+markers",
                        line=dict(color=colors[i % len(colors)], width=3),
                    ))
                elif custom_chart_style == "棒グラフ":
                    fig.add_trace(go.Bar(
                        x=analysis_df[x_axis], y=analysis_df[col],
                        name=col, marker_color=colors[i % len(colors)],
                    ))
                else:  # エリア
                    fig.add_trace(go.Scatter(
                        x=analysis_df[x_axis], y=analysis_df[col],
                        name=col, mode="lines", fill="tonexty",
                        line=dict(color=colors[i % len(colors)]),
                    ))

            fig.update_layout(
                title="カスタムチャート",
                height=CHART_HEIGHT_MAIN,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                margin=dict(t=80, b=40),
                barmode="group" if custom_chart_style == "棒グラフ" else None,
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── F-04: 長期トレンド分析 ───────────────────────

    st.divider()
    st.markdown("### F-04: 長期トレンド分析（直近5年間）")

    if st.button("トレンド分析を実行", type="primary"):
        with st.spinner("AI分析中..."):
            trend = ai.generate_trend_analysis(analysis_df, period_years=5)

        st.markdown(f"**分析サマリー:** {trend['summary']}")

        if trend["highlights"]:
            st.markdown("#### 好調ポイント")
            for h in trend["highlights"]:
                st.success(h)

        if trend["risks"]:
            st.markdown("#### 注意ポイント")
            for r in trend["risks"]:
                st.warning(r)

        if trend["outlook"]:
            st.info(f"**展望:** {trend['outlook']}")

        # 分析完了通知
        ir_db.add_notification(
            user_id, project_id, "analysis_complete",
            "トレンド分析完了",
            "5年間の長期トレンド分析が完了しました。",
        )

        # ステータス更新
        ir_db.update_project_status(project_id, "analyzing")

else:
    st.info("データソースを選択してください。上のタブからExcelまたはEDINETデータを選択できます。")

# ── ナビゲーション ───────────────────────────────────

st.divider()
col_back, col_next = st.columns(2)
with col_back:
    st.link_button(
        "← アップロードに戻る",
        f"/IR_Upload?project_id={project_id}",
        use_container_width=True,
    )
with col_next:
    st.link_button(
        "AI校正・レビューへ進む →",
        f"/IR_Review?project_id={project_id}",
        type="primary",
        use_container_width=True,
    )
