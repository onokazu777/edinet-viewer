# -*- coding: utf-8 -*-
"""
Insight Arc — IR資料作成ダッシュボード

プロジェクト一覧、新規作成、通知確認を行うメインページ。
"""

import streamlit as st
import pandas as pd
import auth_helper as auth
import ir_db_helper as ir_db

st.set_page_config(
    page_title="Insight Arc | IR資料作成",
    page_icon="🎯",
    layout="wide",
)

# ── 初期化 ───────────────────────────────────────────
ir_db.init_ir_tables()
user = auth.require_login()
user_id = user["user_id"]

# ── カスタムCSS ──────────────────────────────────────
st.markdown("""
<style>
    .ia-header {
        background: linear-gradient(135deg, #1a73e8, #6c5ce7);
        color: white;
        padding: 24px 32px;
        border-radius: 16px;
        margin-bottom: 24px;
    }
    .ia-header h1 { color: white; margin: 0; font-size: 2em; }
    .ia-header p { color: rgba(255,255,255,0.85); margin: 8px 0 0; }
    .project-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 12px;
        transition: box-shadow 0.2s;
    }
    .project-card:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .status-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.8em;
        font-weight: 600;
        color: #fff;
    }
    .status-draft { background: #6c757d; }
    .status-analyzing { background: #f9a825; color: #333; }
    .status-review { background: #1a73e8; }
    .status-completed { background: #43a047; }
</style>
""", unsafe_allow_html=True)

# ── ヘッダー ─────────────────────────────────────────
st.markdown(f"""
<div class="ia-header">
    <h1>Insight Arc</h1>
    <p>IR資料作成支援システム &mdash; {user['display_name']} さんのワークスペース</p>
</div>
""", unsafe_allow_html=True)

# ── サイドバー（ログアウト＆通知）────────────────────
with st.sidebar:
    st.markdown("### Insight Arc")
    st.caption(f"ログイン中: {user['display_name']}")

    # 通知バッジ
    unread = ir_db.get_unread_count(user_id)
    if unread > 0:
        st.warning(f"未読通知が {unread} 件あります")

    if st.button("ログアウト", use_container_width=True):
        del st.session_state["ir_user"]
        st.rerun()

    st.divider()

    # 通知一覧
    st.markdown("### 通知")
    notifications = ir_db.get_user_notifications(user_id, limit=10)
    if not notifications.empty:
        if st.button("すべて既読にする", use_container_width=True):
            ir_db.mark_all_notifications_read(user_id)
            st.rerun()

        for _, notif in notifications.iterrows():
            icon = "🔔" if notif["is_read"] == 0 else "✅"
            st.markdown(f"{icon} **{notif['title']}**")
            st.caption(f"{notif['message']}  |  {notif['created_at'][:16]}")
            if notif["is_read"] == 0:
                if st.button("既読", key=f"read_{notif['notification_id']}"):
                    ir_db.mark_notification_read(notif["notification_id"])
                    st.rerun()
    else:
        st.caption("通知はありません")

# ── プロジェクト新規作成 ──────────────────────────────

st.markdown("### 新規プロジェクト作成")

with st.form("new_project_form"):
    col1, col2 = st.columns(2)
    with col1:
        title = st.text_input("プロジェクト名", placeholder="例: 2025年3月期 決算説明資料")
    with col2:
        target_company = st.text_input("対象企業名", placeholder="例: 株式会社サンプル")

    col3, col4 = st.columns(2)
    with col3:
        sec_code = st.text_input("証券コード（任意）", placeholder="例: 7203")
    with col4:
        description = st.text_input("説明（任意）", placeholder="プロジェクトの概要")

    submitted = st.form_submit_button("プロジェクト作成", type="primary", use_container_width=True)

    if submitted:
        if not title.strip():
            st.error("プロジェクト名を入力してください。")
        else:
            project_id = ir_db.create_project(
                user_id=user_id,
                title=title.strip(),
                description=description.strip(),
                target_company=target_company.strip(),
                sec_code=sec_code.strip(),
            )
            st.success(f"プロジェクト「{title}」を作成しました。（ID: {project_id}）")
            st.rerun()

# ── プロジェクト一覧 ──────────────────────────────────

st.divider()
st.markdown("### プロジェクト一覧")

projects = ir_db.get_user_projects(user_id)

if projects.empty:
    st.info("プロジェクトがまだありません。上のフォームから新規作成してください。")
else:
    STATUS_MAP = {
        "draft": ("下書き", "status-draft"),
        "analyzing": ("AI分析中", "status-analyzing"),
        "review": ("レビュー中", "status-review"),
        "completed": ("完了", "status-completed"),
    }

    for _, proj in projects.iterrows():
        status_label, status_class = STATUS_MAP.get(
            proj["status"], ("不明", "status-draft")
        )

        col_info, col_actions = st.columns([3, 1])

        with col_info:
            st.markdown(
                f'<span class="status-badge {status_class}">{status_label}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(f"**{proj['title']}**")
            meta_parts = []
            if proj["target_company"]:
                meta_parts.append(f"企業: {proj['target_company']}")
            if proj["sec_code"]:
                meta_parts.append(f"コード: {proj['sec_code']}")
            meta_parts.append(f"ファイル: {proj['file_count']}件")
            meta_parts.append(f"更新: {proj['updated_at'][:16]}")
            st.caption(" | ".join(meta_parts))

        with col_actions:
            st.markdown("<br>", unsafe_allow_html=True)
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.link_button(
                    "編集",
                    f"/IR_Upload?project_id={proj['project_id']}",
                    use_container_width=True,
                )
            with col_b:
                st.link_button(
                    "分析",
                    f"/IR_Editor?project_id={proj['project_id']}",
                    use_container_width=True,
                )
            with col_c:
                st.link_button(
                    "レビュー",
                    f"/IR_Review?project_id={proj['project_id']}",
                    use_container_width=True,
                )

        st.divider()

    # プロジェクト削除（expanderに隠す）
    with st.expander("プロジェクト管理", expanded=False):
        del_project = st.selectbox(
            "削除するプロジェクト",
            [(p["project_id"], p["title"]) for _, p in projects.iterrows()],
            format_func=lambda x: f"{x[0]}: {x[1]}",
            key="del_project_select",
        )
        if st.button("削除", type="secondary"):
            ir_db.delete_project(del_project[0])
            st.success(f"プロジェクト「{del_project[1]}」を削除しました。")
            st.rerun()

# ── フッター ─────────────────────────────────────────
st.divider()
st.caption("Insight Arc — IR資料作成支援システム v1.0")
