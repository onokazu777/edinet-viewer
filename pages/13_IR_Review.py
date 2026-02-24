# -*- coding: utf-8 -*-
"""
Insight Arc — F-05/F-07/F-08 AI校正・レビュー & 学習ボタン

AI校正・指摘の表示、学習ボタンによるフィードバック、
最終書き出しまでの処理フローを実装。
"""

import json

import pandas as pd
import streamlit as st

import auth_helper as auth
import ir_db_helper as ir_db
import db_helper as db
from ai_mock import MockAIEngine

st.set_page_config(
    page_title="AI校正・レビュー | Insight Arc",
    page_icon="🔍",
    layout="wide",
)

# ── カスタムCSS（学習ボタンのフローティング配置）─────
st.markdown("""
<style>
    .suggestion-card {
        background: #f8f9fa;
        border-left: 4px solid #1a73e8;
        border-radius: 0 8px 8px 0;
        padding: 16px 20px;
        margin-bottom: 12px;
        position: relative;
    }
    .suggestion-card.error { border-left-color: #e53935; }
    .suggestion-card.warning { border-left-color: #f9a825; }
    .suggestion-card.info { border-left-color: #1a73e8; }
    .severity-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 8px;
        font-size: 0.75em;
        font-weight: 600;
        color: #fff;
    }
    .severity-error { background: #e53935; }
    .severity-warning { background: #f9a825; color: #333; }
    .severity-info { background: #1a73e8; }
    .learning-rule-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 8px;
        font-size: 0.75em;
        background: #e8f5e9;
        color: #2e7d32;
        margin-left: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ── 初期化 ───────────────────────────────────────────
ir_db.init_ir_tables()
user = auth.require_login()
user_id = user["user_id"]
ai = MockAIEngine()

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
    index=default_idx, key="review_project",
)
project_id = project_options[selected_label]
project = ir_db.get_project(project_id)

st.title(f"AI校正・レビュー — {project['title']}")

# ── AI分析実行 ───────────────────────────────────────

st.markdown("### F-05: AI校正・指摘")
st.caption("過去の傾向に基づき、数値の乖離や表現の不備をリアルタイムで検知します。")

# 学習ルール取得（抑制対象）
learning_rules = ir_db.get_project_learning_rules(project_id)
suppressed_rules = list(learning_rules["rule_type"].unique()) if not learning_rules.empty else []

col_analyze, col_status = st.columns([3, 1])
with col_analyze:
    run_analysis = st.button("AI分析を実行", type="primary", use_container_width=True)
with col_status:
    existing_suggestions = ir_db.get_project_suggestions(project_id)
    if not existing_suggestions.empty:
        st.caption(f"既存の指摘: {len(existing_suggestions)}件")

if run_analysis:
    with st.spinner("AI分析を実行中..."):
        new_suggestions = []

        # Excelデータの分析
        excel_data = ir_db.get_project_excel_data(project_id)
        for _, row in excel_data.iterrows():
            try:
                records = json.loads(row["data_json"])
                df = pd.DataFrame(records)
                suggestions = ai.analyze_financial_data(df, suppressed_rules)
                new_suggestions.extend(suggestions)
            except Exception:
                pass

        # EDINETデータの分析（証券コードがあれば）
        sec_code = project.get("sec_code", "")
        if sec_code:
            edinet_fin = db.get_key_financials(sec_code)
            if not edinet_fin.empty:
                if 1 in edinet_fin["is_consolidated"].values:
                    edinet_fin = edinet_fin[edinet_fin["is_consolidated"] == 1]
                edinet_fin = edinet_fin.sort_values("period_end")
                yen_cols = ["sales", "operating_income", "ordinary_income", "net_income",
                            "total_assets", "net_assets"]
                for col in yen_cols:
                    if col in edinet_fin.columns:
                        edinet_fin[col] = edinet_fin[col] / 1e8
                suggestions = ai.analyze_financial_data(edinet_fin, suppressed_rules)
                new_suggestions.extend(suggestions)

            # テキストブロック分析
            text_blocks = db.get_company_text_blocks(sec_code)
            if not text_blocks.empty:
                latest_period = text_blocks["period_end"].max()
                latest_texts = text_blocks[text_blocks["period_end"] == latest_period]
                for _, tb in latest_texts.iterrows():
                    text_sugg = ai.analyze_text_content(
                        tb.get("text_content", ""), suppressed_rules
                    )
                    new_suggestions.extend(text_sugg)

        # 新しい指摘をDBに保存
        saved_count = 0
        for s in new_suggestions:
            ir_db.add_suggestion(
                project_id=project_id,
                category=s["category"],
                severity=s["severity"],
                title=s["title"],
                detail=s.get("detail", ""),
                target_element=s.get("target_element", ""),
                suggested_fix=s.get("suggested_fix", ""),
            )
            saved_count += 1

    # 通知
    ir_db.add_notification(
        user_id, project_id, "analysis_complete",
        "AI校正完了",
        f"{saved_count}件の指摘が検出されました。",
    )

    ir_db.update_project_status(project_id, "review")
    st.success(f"AI分析完了: {saved_count}件の指摘が追加されました。")
    st.rerun()

# ── 指摘リスト表示 ───────────────────────────────────

st.divider()

show_dismissed = st.checkbox("無視した指摘も表示", key="show_dismissed")
suggestions = ir_db.get_project_suggestions(project_id, include_dismissed=show_dismissed)

if suggestions.empty:
    st.info("指摘はありません。「AI分析を実行」ボタンで分析を開始してください。")
else:
    # 重要度別カウント
    severity_counts = suggestions["severity"].value_counts().to_dict()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("合計", len(suggestions))
    with col2:
        st.metric("エラー", severity_counts.get("error", 0))
    with col3:
        st.metric("警告", severity_counts.get("warning", 0))
    with col4:
        st.metric("情報", severity_counts.get("info", 0))

    st.markdown("---")

    # カテゴリフィルタ
    categories = ["すべて"] + sorted(suggestions["category"].unique().tolist())
    selected_category = st.selectbox("カテゴリで絞り込み", categories, key="cat_filter")

    if selected_category != "すべて":
        display_suggestions = suggestions[suggestions["category"] == selected_category]
    else:
        display_suggestions = suggestions

    # 各指摘を表示
    for idx, (_, s) in enumerate(display_suggestions.iterrows()):
        severity_class = f"severity-{s['severity']}"
        card_class = s["severity"]
        dismissed = s["is_dismissed"] == 1
        has_rule = s.get("has_learning_rule", 0) == 1

        # 指摘カード
        with st.container():
            col_content, col_actions = st.columns([4, 1])

            with col_content:
                # ヘッダー
                severity_label = {"error": "エラー", "warning": "警告", "info": "情報"}.get(
                    s["severity"], s["severity"]
                )

                header_html = f'<span class="severity-badge {severity_class}">{severity_label}</span>'
                header_html += f' <strong>{s["title"]}</strong>'
                if has_rule:
                    header_html += '<span class="learning-rule-badge">学習済み</span>'
                if dismissed:
                    header_html += ' <span style="color:#999;font-size:0.8em">（無視済み）</span>'

                st.markdown(header_html, unsafe_allow_html=True)
                st.caption(f"カテゴリ: {s['category']}  |  対象: {s.get('target_element', '-')}")

                if s["detail"]:
                    st.markdown(f"> {s['detail']}")

                if s["suggested_fix"]:
                    st.info(f"**提案:** {s['suggested_fix']}")

            # F-07/F-08: 学習ボタン（右端配置）
            with col_actions:
                if not dismissed:
                    # 「無視」ボタン（一時的に非表示にする）
                    if st.button("無視", key=f"dismiss_{s['suggestion_id']}_{idx}",
                                 use_container_width=True):
                        ir_db.dismiss_suggestion(s["suggestion_id"])
                        st.rerun()

                    # 「学習ボタン」（F-07: 今後もこのルールを適用しない）
                    if st.button(
                        "今後も無視",
                        key=f"learn_{s['suggestion_id']}_{idx}",
                        help="F-07: この指摘ルールを今後この資料では適用しない",
                        use_container_width=True,
                    ):
                        # F-08: 効果はこの資料内のみ
                        ir_db.add_learning_rule(
                            project_id=project_id,
                            suggestion_id=s["suggestion_id"],
                            rule_type=s.get("category", "unknown"),
                            rule_detail=f"ユーザーが「{s['title']}」の指摘ルールを無効化",
                        )
                        st.rerun()

            st.divider()

# ── 学習ルール管理（F-08）────────────────────────────

with st.expander("学習ルール管理（F-08: この資料で無視するルール一覧）", expanded=False):
    rules = ir_db.get_project_learning_rules(project_id)

    if rules.empty:
        st.caption("学習ルールはまだありません。")
    else:
        st.caption(f"F-08: 以下のルールはこの資料でのみ適用されます（他の資料には影響しません）")

        for _, rule in rules.iterrows():
            st.markdown(
                f"- **{rule['suggestion_title']}** ({rule['category']}) — "
                f"登録日: {rule['created_at'][:16]}"
            )

# ── 最終書き出し（処理フロー最終段階）────────────────

st.divider()
st.markdown("### 最終書き出し")
st.caption("処理フロー: データ投入 → AI解析 → 完了通知 → 確認・学習 → **最終書き出し**")

active_suggestions = ir_db.get_project_suggestions(project_id, include_dismissed=False)
active_errors = active_suggestions[active_suggestions["severity"] == "error"] if not active_suggestions.empty else pd.DataFrame()

if not active_errors.empty:
    st.warning(f"未解決のエラーが {len(active_errors)} 件あります。書き出し前に確認してください。")

col_export1, col_export2 = st.columns(2)

with col_export1:
    if st.button("分析レポートをダウンロード", use_container_width=True):
        # レポート生成
        all_suggestions = ir_db.get_project_suggestions(project_id, include_dismissed=True)
        report_lines = [
            f"# Insight Arc — AI校正レポート",
            f"## プロジェクト: {project['title']}",
            f"対象企業: {project.get('target_company', '-')}",
            f"証券コード: {project.get('sec_code', '-')}",
            f"",
            f"## 指摘一覧（{len(all_suggestions)}件）",
            f"",
        ]

        if not all_suggestions.empty:
            for _, s in all_suggestions.iterrows():
                status = "無視" if s["is_dismissed"] else "未対応"
                report_lines.append(
                    f"### [{s['severity'].upper()}] {s['title']} ({status})"
                )
                report_lines.append(f"- カテゴリ: {s['category']}")
                report_lines.append(f"- 対象: {s.get('target_element', '-')}")
                if s["detail"]:
                    report_lines.append(f"- 詳細: {s['detail']}")
                if s["suggested_fix"]:
                    report_lines.append(f"- 提案: {s['suggested_fix']}")
                report_lines.append("")

        # 学習ルール
        rules = ir_db.get_project_learning_rules(project_id)
        if not rules.empty:
            report_lines.append("## 学習ルール")
            for _, r in rules.iterrows():
                report_lines.append(f"- {r['suggestion_title']} ({r['category']})")

        report_text = "\n".join(report_lines)

        st.download_button(
            "レポートをダウンロード (.md)",
            report_text.encode("utf-8"),
            file_name=f"insight_arc_report_{project_id}.md",
            mime="text/markdown",
        )

with col_export2:
    if st.button("プロジェクトを完了にする", use_container_width=True):
        ir_db.update_project_status(project_id, "completed")
        ir_db.add_notification(
            user_id, project_id, "project_completed",
            "プロジェクト完了",
            f"「{project['title']}」が完了しました。",
        )
        st.success("プロジェクトを完了にしました。")
        st.balloons()

# ── ナビゲーション ───────────────────────────────────

st.divider()
col_back, col_dash = st.columns(2)
with col_back:
    st.link_button(
        "← データ分析に戻る",
        f"/IR_Editor?project_id={project_id}",
        use_container_width=True,
    )
with col_dash:
    st.link_button("ダッシュボードに戻る", "/IR_Dashboard", use_container_width=True)
