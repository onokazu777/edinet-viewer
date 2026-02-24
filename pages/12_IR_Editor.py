# -*- coding: utf-8 -*-
"""
Insight Arc — F-02/F-04/F-06 データ分析・グラフ同期エディタ

Excel データとグラフの動的連動、5年トレンド分析、
スケーリング表示を行うページ。

F-02: Excelシート → スライド・グラフへのマッピング設定
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

GRAPH_TYPE_OPTIONS = {
    "bar": "棒グラフ",
    "line": "折れ線グラフ",
    "bar_line": "棒＋折れ線（売上・利益向け）",
    "area": "エリアチャート",
    "grouped_bar": "グループ棒グラフ",
}


def _build_chart(graph_type: str, df: pd.DataFrame,
                 x_col: str, y_cols: list[str],
                 title: str = "", height: int = CHART_HEIGHT_MAIN) -> go.Figure:
    """マッピング設定からPlotlyチャートを生成"""
    colors = ["#1a73e8", "#e53935", "#43a047", "#f9a825", "#7b1fa2"]

    if graph_type == "bar_line" and len(y_cols) >= 2:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(
            go.Bar(x=df[x_col], y=df[y_cols[0]], name=y_cols[0],
                   marker_color=colors[0], opacity=0.7),
            secondary_y=False,
        )
        for i, col in enumerate(y_cols[1:], 1):
            fig.add_trace(
                go.Scatter(x=df[x_col], y=df[col], name=col,
                           mode="lines+markers",
                           line=dict(color=colors[i % len(colors)], width=3)),
                secondary_y=True,
            )
        fig.update_yaxes(title_text=y_cols[0], secondary_y=False)
        fig.update_yaxes(title_text="副軸", secondary_y=True)
    else:
        fig = go.Figure()
        for i, col in enumerate(y_cols):
            if graph_type == "line":
                fig.add_trace(go.Scatter(
                    x=df[x_col], y=df[col], name=col,
                    mode="lines+markers",
                    line=dict(color=colors[i % len(colors)], width=3),
                ))
            elif graph_type == "area":
                fig.add_trace(go.Scatter(
                    x=df[x_col], y=df[col], name=col,
                    mode="lines", fill="tonexty",
                    line=dict(color=colors[i % len(colors)]),
                ))
            else:  # bar / grouped_bar
                fig.add_trace(go.Bar(
                    x=df[x_col], y=df[col], name=col,
                    marker_color=colors[i % len(colors)],
                ))

        if graph_type in ("bar", "grouped_bar"):
            fig.update_layout(barmode="group")

    fig.update_layout(
        title=title, height=height,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=80, b=40),
    )
    return fig


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

# ── データソース一覧を取得 ────────────────────────────

excel_data = ir_db.get_project_excel_data(project_id)

# EDINET データも取得してデータソース一覧に追加
edinet_data_id = None  # EDINET用の仮ID
edinet_df = pd.DataFrame()
sec_code = project.get("sec_code", "")

if sec_code:
    edinet_fin = db.get_key_financials(sec_code)
    if not edinet_fin.empty:
        if 1 in edinet_fin["is_consolidated"].values:
            edinet_fin = edinet_fin[edinet_fin["is_consolidated"] == 1]
        edinet_fin = edinet_fin.sort_values("period_end")
        if len(edinet_fin) > 20:
            edinet_fin = edinet_fin.tail(20)
        yen_cols = ["sales", "operating_income", "ordinary_income", "net_income",
                    "total_assets", "net_assets",
                    "operating_cf", "investing_cf", "financing_cf"]
        for col in yen_cols:
            if col in edinet_fin.columns:
                edinet_fin[col] = edinet_fin[col] / 1e8
        edinet_df = edinet_fin

# ══════════════════════════════════════════════════════
#  セクション1: データソース確認
# ══════════════════════════════════════════════════════

st.markdown("### データソース")

tab_excel, tab_edinet = st.tabs(["📁 アップロードExcel", "📊 EDINET データ"])

with tab_excel:
    if excel_data.empty:
        st.info("Excelデータがありません。先にファイルをアップロードしてください。")
        st.link_button("アップロードページへ", f"/IR_Upload?project_id={project_id}")
    else:
        st.caption(f"{len(excel_data)} 件のデータセットがあります。")
        for _, row in excel_data.iterrows():
            with st.expander(f"📄 {row['label']}（ID: {row['data_id']}）"):
                try:
                    records = json.loads(row["data_json"])
                    df_preview = pd.DataFrame(records)
                    st.dataframe(df_preview, use_container_width=True, height=150)
                    st.caption(f"列: {', '.join(df_preview.columns)} | 行数: {len(df_preview)}")
                except Exception as e:
                    st.error(f"データ読み込みエラー: {e}")

with tab_edinet:
    if sec_code and not edinet_df.empty:
        st.markdown(f"#### {sec_code} の財務データ（直近5年間）")
        st.dataframe(edinet_df, use_container_width=True, height=200)
    elif sec_code:
        st.warning(f"証券コード {sec_code} のEDINETデータが見つかりません。")
    else:
        st.info("プロジェクトに証券コードを設定するとEDINETデータを利用できます。")

# ══════════════════════════════════════════════════════
#  セクション2: F-02 グラフマッピング設定
# ══════════════════════════════════════════════════════

st.divider()
st.markdown("### F-02: グラフマッピング設定")
st.caption(
    "Excelのどのデータを、どのスライドのどのグラフに使うかを設定します。\n"
    "Excel更新時にグラフ側が自動で最新化されます。"
)

# データソース選択肢を構築
data_source_options = {}
for _, row in excel_data.iterrows():
    data_source_options[f"Excel: {row['label']} (ID:{row['data_id']})"] = row["data_id"]

if excel_data.empty and edinet_df.empty:
    st.info("マッピングにはデータソースが必要です。Excelをアップロードするか、証券コードを設定してください。")
else:
    # ── 新規マッピング追加フォーム ─────────────────────

    with st.expander("新しいグラフマッピングを追加", expanded=not excel_data.empty):
        with st.form("add_mapping_form"):
            st.markdown("**1. データソースを選択**")
            if not data_source_options:
                st.warning("Excelデータをアップロードしてください。")
                st.form_submit_button("保存", disabled=True)
            else:
                selected_source = st.selectbox(
                    "データソース",
                    list(data_source_options.keys()),
                    key="mapping_source",
                )
                selected_data_id = data_source_options[selected_source]

                # 選択されたデータの列を取得
                sel_row = excel_data[excel_data["data_id"] == selected_data_id].iloc[0]
                try:
                    sel_records = json.loads(sel_row["data_json"])
                    sel_df = pd.DataFrame(sel_records)
                    sel_all_cols = sel_df.columns.tolist()
                    sel_numeric_cols = sel_df.select_dtypes(include="number").columns.tolist()
                except Exception:
                    sel_all_cols = []
                    sel_numeric_cols = []

                st.markdown("**2. 配置先スライドとグラフ名を指定**")
                col_slide, col_name = st.columns(2)
                with col_slide:
                    slide_number = st.number_input(
                        "スライド番号", min_value=1, max_value=100, value=1,
                        key="mapping_slide",
                    )
                with col_name:
                    graph_name = st.text_input(
                        "グラフ名",
                        placeholder="例: 売上高・営業利益推移",
                        key="mapping_graph_name",
                    )

                st.markdown("**3. グラフの種類と使用する列を選択**")
                col_type, col_x = st.columns(2)
                with col_type:
                    graph_type = st.selectbox(
                        "グラフタイプ",
                        list(GRAPH_TYPE_OPTIONS.keys()),
                        format_func=lambda x: GRAPH_TYPE_OPTIONS[x],
                        key="mapping_graph_type",
                    )
                with col_x:
                    x_column = st.selectbox(
                        "X軸（期間列）",
                        sel_all_cols,
                        key="mapping_x_col",
                    )

                y_columns = st.multiselect(
                    "Y軸（数値列）— 複数選択可",
                    sel_numeric_cols,
                    key="mapping_y_cols",
                )

                if graph_type == "bar_line":
                    st.caption("棒＋折れ線: 最初のY軸列が棒グラフ、残りが折れ線になります。")

                submitted = st.form_submit_button("マッピングを保存", type="primary",
                                                   use_container_width=True)
                if submitted:
                    if not graph_name.strip():
                        st.error("グラフ名を入力してください。")
                    elif not y_columns:
                        st.error("Y軸の列を1つ以上選択してください。")
                    else:
                        ir_db.save_graph_mapping(
                            project_id=project_id,
                            data_id=selected_data_id,
                            slide_number=slide_number,
                            graph_name=graph_name.strip(),
                            graph_type=graph_type,
                            x_column=x_column,
                            y_columns=y_columns,
                        )
                        ir_db.add_notification(
                            user_id, project_id, "mapping_saved",
                            "グラフマッピング保存",
                            f"スライド{slide_number}「{graph_name}」のマッピングを保存しました。",
                        )
                        st.success(f"スライド{slide_number}「{graph_name}」のマッピングを保存しました。")
                        st.rerun()

# ══════════════════════════════════════════════════════
#  セクション3: 保存済みマッピング一覧 & グラフプレビュー
# ══════════════════════════════════════════════════════

st.divider()
st.markdown("### 保存済みグラフマッピング")
st.caption("F-02: Excelデータ更新時、ここに表示されるグラフも自動で最新化されます。")

mappings = ir_db.get_project_graph_mappings(project_id)

if mappings.empty:
    st.info("グラフマッピングがまだありません。上のフォームから追加してください。")
else:
    # スライド番号順にグループ化
    slide_numbers = sorted(mappings["slide_number"].unique())

    for slide_no in slide_numbers:
        st.markdown(f"---")
        st.markdown(f"## スライド {slide_no}")

        slide_mappings = mappings[mappings["slide_number"] == slide_no]

        for _, m in slide_mappings.iterrows():
            col_chart, col_meta = st.columns([3, 1])

            with col_meta:
                st.markdown(f"**{m['graph_name']}**")
                st.caption(f"タイプ: {GRAPH_TYPE_OPTIONS.get(m['graph_type'], m['graph_type'])}")
                st.caption(f"データ: {m['data_label']}")
                st.caption(f"X軸: {m['x_column']}")
                try:
                    y_cols_list = json.loads(m["y_columns_json"])
                    st.caption(f"Y軸: {', '.join(y_cols_list)}")
                except Exception:
                    y_cols_list = []

                if st.button("削除", key=f"del_map_{m['mapping_id']}"):
                    ir_db.delete_graph_mapping(m["mapping_id"])
                    st.rerun()

            with col_chart:
                # データを読み込んでグラフを描画
                try:
                    data_row = excel_data[excel_data["data_id"] == m["data_id"]]
                    if not data_row.empty:
                        records = json.loads(data_row.iloc[0]["data_json"])
                        chart_df = pd.DataFrame(records)

                        if m["x_column"] in chart_df.columns and y_cols_list:
                            valid_y = [c for c in y_cols_list if c in chart_df.columns]
                            if valid_y:
                                fig = _build_chart(
                                    m["graph_type"], chart_df,
                                    m["x_column"], valid_y,
                                    title=f"スライド{slide_no}: {m['graph_name']}",
                                    height=CHART_HEIGHT_SUB,
                                )
                                st.plotly_chart(fig, use_container_width=True)
                            else:
                                st.warning("Y軸の列がデータに見つかりません。")
                        else:
                            st.warning("マッピングの列がデータに存在しません。Excelを確認してください。")
                    else:
                        st.warning(f"データID {m['data_id']} が見つかりません。")
                except Exception as e:
                    st.error(f"グラフ描画エラー: {e}")

# ══════════════════════════════════════════════════════
#  セクション4: F-04 長期トレンド分析
# ══════════════════════════════════════════════════════

st.divider()
st.markdown("### F-04: 長期トレンド分析（直近5年間）")

# トレンド分析用のデータソース選択
trend_source = st.radio(
    "分析対象データ",
    ["EDINET データ"] + [f"Excel: {row['label']}" for _, row in excel_data.iterrows()],
    horizontal=True,
    key="trend_source",
)

trend_df = pd.DataFrame()
if trend_source == "EDINET データ" and not edinet_df.empty:
    trend_df = edinet_df
elif trend_source.startswith("Excel:"):
    for _, row in excel_data.iterrows():
        if f"Excel: {row['label']}" == trend_source:
            try:
                records = json.loads(row["data_json"])
                trend_df = pd.DataFrame(records)
            except Exception:
                pass
            break

if not trend_df.empty:
    if st.button("トレンド分析を実行", type="primary"):
        with st.spinner("AI分析中..."):
            trend = ai.generate_trend_analysis(trend_df, period_years=5)

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

        ir_db.add_notification(
            user_id, project_id, "analysis_complete",
            "トレンド分析完了",
            "5年間の長期トレンド分析が完了しました。",
        )
        ir_db.update_project_status(project_id, "analyzing")
else:
    if trend_source == "EDINET データ":
        st.info("EDINETデータがありません。プロジェクトの証券コードを確認してください。")
    else:
        st.info("データの読み込みに失敗しました。")

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
