# -*- coding: utf-8 -*-
"""
Insight Arc — 簡易認証ヘルパー

ID/パスワードによるシンプルなセッション認証を提供する。
ユーザー情報は SQLite の ir_users テーブルに保存。
"""

import hashlib
import sqlite3
import streamlit as st
from pathlib import Path

IR_DB_PATH = Path(__file__).parent / "data" / "insight_arc.sqlite3"


def _get_conn() -> sqlite3.Connection:
    IR_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(IR_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_auth_tables():
    """認証テーブルを初期化し、デモユーザーを作成"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # デモユーザーがなければ作成
        existing = conn.execute(
            "SELECT 1 FROM ir_users WHERE username = ?", ("demo",)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO ir_users (username, password_hash, display_name) VALUES (?, ?, ?)",
                ("demo", _hash_password("demo123"), "デモユーザー"),
            )
        conn.commit()
    finally:
        conn.close()


def authenticate(username: str, password: str) -> dict | None:
    """認証を行い、成功時にユーザー情報を返す"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT user_id, username, display_name FROM ir_users WHERE username = ? AND password_hash = ?",
            (username, _hash_password(password)),
        ).fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def register_user(username: str, password: str, display_name: str) -> bool:
    """新規ユーザーを登録"""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO ir_users (username, password_hash, display_name) VALUES (?, ?, ?)",
            (username, _hash_password(password), display_name),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def require_login():
    """ログインが必要なページで呼び出す。未ログインならログインフォームを表示して停止。"""
    init_auth_tables()

    if "ir_user" in st.session_state and st.session_state["ir_user"]:
        return st.session_state["ir_user"]

    st.markdown("## Insight Arc - ログイン")
    st.caption("IR資料作成支援システムを利用するにはログインが必要です。")

    tab_login, tab_register = st.tabs(["ログイン", "新規登録"])

    with tab_login:
        with st.form("login_form"):
            username = st.text_input("ユーザーID", placeholder="demo")
            password = st.text_input("パスワード", type="password", placeholder="demo123")
            submitted = st.form_submit_button("ログイン", type="primary", use_container_width=True)

            if submitted:
                user = authenticate(username, password)
                if user:
                    st.session_state["ir_user"] = user
                    st.rerun()
                else:
                    st.error("ユーザーIDまたはパスワードが正しくありません。")

        st.info("デモアカウント: ID=`demo` / PW=`demo123`")

    with tab_register:
        with st.form("register_form"):
            new_username = st.text_input("ユーザーID（英数字）", key="reg_username")
            new_display = st.text_input("表示名", key="reg_display")
            new_password = st.text_input("パスワード", type="password", key="reg_password")
            new_password2 = st.text_input("パスワード（確認）", type="password", key="reg_password2")
            reg_submitted = st.form_submit_button("登録", use_container_width=True)

            if reg_submitted:
                if not new_username or not new_password or not new_display:
                    st.error("全項目を入力してください。")
                elif new_password != new_password2:
                    st.error("パスワードが一致しません。")
                elif len(new_password) < 4:
                    st.error("パスワードは4文字以上にしてください。")
                else:
                    if register_user(new_username, new_password, new_display):
                        st.success("登録完了しました。ログインタブからログインしてください。")
                    else:
                        st.error("このユーザーIDは既に使用されています。")

    st.stop()
