# -*- coding: utf-8 -*-
"""
Insight Arc — IR資料作成支援 DBヘルパー

IR資料プロジェクト、アップロードファイル、AI指摘、
学習ルール、通知等を管理するユーティリティ群。
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

IR_DB_PATH = Path(__file__).parent / "data" / "insight_arc.sqlite3"
UPLOAD_DIR = Path(__file__).parent / "data" / "ir_uploads"


def _get_conn() -> sqlite3.Connection:
    IR_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(IR_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    conn = _get_conn()
    try:
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


def init_ir_tables():
    """IR関連テーブルを初期化"""
    conn = _get_conn()
    try:
        # プロジェクト（IR資料単位）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_projects (
                project_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                target_company TEXT,
                sec_code TEXT,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # アップロードファイル
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_uploads (
                upload_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                file_type TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                file_size INTEGER,
                metadata_json TEXT,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ir_projects(project_id)
            )
        """)

        # Excel データ同期テーブル
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_excel_data (
                data_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                upload_id INTEGER NOT NULL,
                sheet_name TEXT,
                cell_range TEXT,
                data_json TEXT NOT NULL,
                data_type TEXT DEFAULT 'kpi',
                label TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ir_projects(project_id),
                FOREIGN KEY (upload_id) REFERENCES ir_uploads(upload_id)
            )
        """)

        # AI指摘・提案
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_suggestions (
                suggestion_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                severity TEXT DEFAULT 'info',
                title TEXT NOT NULL,
                detail TEXT,
                target_element TEXT,
                suggested_fix TEXT,
                is_dismissed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ir_projects(project_id)
            )
        """)

        # 学習ルール（F-07/F-08: 資料単位でのルール無視設定）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_learning_rules (
                rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                suggestion_id INTEGER NOT NULL,
                rule_type TEXT NOT NULL,
                rule_detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ir_projects(project_id),
                FOREIGN KEY (suggestion_id) REFERENCES ir_suggestions(suggestion_id)
            )
        """)

        # 通知（F-09）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_notifications (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id INTEGER,
                notif_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 画像配置情報（F-03）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_image_placements (
                placement_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                upload_id INTEGER NOT NULL,
                slide_number INTEGER,
                position_x REAL,
                position_y REAL,
                width REAL,
                height REAL,
                context_label TEXT,
                ai_confidence REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ir_projects(project_id),
                FOREIGN KEY (upload_id) REFERENCES ir_uploads(upload_id)
            )
        """)

        # グラフマッピング（F-02: Excelデータ→スライド・グラフの紐付け）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_graph_mappings (
                mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                data_id INTEGER NOT NULL,
                slide_number INTEGER NOT NULL,
                graph_name TEXT NOT NULL,
                graph_type TEXT NOT NULL DEFAULT 'bar',
                x_column TEXT,
                y_columns_json TEXT,
                chart_config_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES ir_projects(project_id),
                FOREIGN KEY (data_id) REFERENCES ir_excel_data(data_id)
            )
        """)

        conn.commit()
    finally:
        conn.close()


# ── プロジェクト操作 ─────────────────────────────────

def create_project(user_id: int, title: str, description: str = "",
                   target_company: str = "", sec_code: str = "") -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ir_projects
               (user_id, title, description, target_company, sec_code)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, title, description, target_company, sec_code),
        )
        conn.commit()
        project_id = cursor.lastrowid

        # 通知を作成
        add_notification(
            user_id, project_id, "project_created",
            "プロジェクト作成完了",
            f"「{title}」プロジェクトが作成されました。",
        )
        return project_id
    finally:
        conn.close()


def get_user_projects(user_id: int) -> pd.DataFrame:
    return _query_df(
        """SELECT p.*, COUNT(u.upload_id) as file_count
           FROM ir_projects p
           LEFT JOIN ir_uploads u ON p.project_id = u.project_id
           WHERE p.user_id = ?
           GROUP BY p.project_id
           ORDER BY p.updated_at DESC""",
        (user_id,),
    )


def get_project(project_id: int) -> dict | None:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM ir_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_project_status(project_id: int, status: str):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE ir_projects SET status = ?, updated_at = ? WHERE project_id = ?",
            (status, datetime.now().isoformat(), project_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_project(project_id: int):
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM ir_graph_mappings WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ir_learning_rules WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ir_suggestions WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ir_image_placements WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ir_excel_data WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ir_uploads WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ir_notifications WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM ir_projects WHERE project_id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()


# ── ファイルアップロード操作 ─────────────────────────

def save_upload(project_id: int, file_type: str, original_name: str,
                file_bytes: bytes, metadata: dict = None) -> int:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{project_id}_{timestamp}_{original_name}"
    stored_path = UPLOAD_DIR / safe_name

    stored_path.write_bytes(file_bytes)

    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ir_uploads
               (project_id, file_type, original_name, stored_path, file_size, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, file_type, original_name, str(stored_path),
             len(file_bytes), json.dumps(metadata or {}, ensure_ascii=False)),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_project_uploads(project_id: int) -> pd.DataFrame:
    return _query_df(
        """SELECT * FROM ir_uploads WHERE project_id = ?
           ORDER BY uploaded_at DESC""",
        (project_id,),
    )


def delete_upload(upload_id: int):
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT stored_path FROM ir_uploads WHERE upload_id = ?", (upload_id,)
        ).fetchone()
        if row:
            path = Path(row["stored_path"])
            if path.exists():
                path.unlink()
        conn.execute("DELETE FROM ir_image_placements WHERE upload_id = ?", (upload_id,))
        conn.execute("DELETE FROM ir_excel_data WHERE upload_id = ?", (upload_id,))
        conn.execute("DELETE FROM ir_uploads WHERE upload_id = ?", (upload_id,))
        conn.commit()
    finally:
        conn.close()


# ── Excelデータ同期操作 ──────────────────────────────

def save_excel_data(project_id: int, upload_id: int, sheet_name: str,
                    data: list[dict], label: str = "", data_type: str = "kpi") -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ir_excel_data
               (project_id, upload_id, sheet_name, data_json, label, data_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (project_id, upload_id, sheet_name,
             json.dumps(data, ensure_ascii=False, default=str), label, data_type),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_project_excel_data(project_id: int) -> pd.DataFrame:
    return _query_df(
        "SELECT * FROM ir_excel_data WHERE project_id = ? ORDER BY data_id",
        (project_id,),
    )


# ── グラフマッピング操作（F-02）─────────────────────

def save_graph_mapping(project_id: int, data_id: int, slide_number: int,
                       graph_name: str, graph_type: str,
                       x_column: str, y_columns: list[str],
                       chart_config: dict = None) -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ir_graph_mappings
               (project_id, data_id, slide_number, graph_name, graph_type,
                x_column, y_columns_json, chart_config_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, data_id, slide_number, graph_name, graph_type,
             x_column, json.dumps(y_columns, ensure_ascii=False),
             json.dumps(chart_config or {}, ensure_ascii=False)),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_project_graph_mappings(project_id: int) -> pd.DataFrame:
    return _query_df(
        """SELECT gm.*, ed.label as data_label, ed.sheet_name
           FROM ir_graph_mappings gm
           JOIN ir_excel_data ed ON gm.data_id = ed.data_id
           WHERE gm.project_id = ?
           ORDER BY gm.slide_number, gm.mapping_id""",
        (project_id,),
    )


def update_graph_mapping(mapping_id: int, slide_number: int,
                         graph_name: str, graph_type: str,
                         x_column: str, y_columns: list[str],
                         chart_config: dict = None):
    conn = _get_conn()
    try:
        conn.execute(
            """UPDATE ir_graph_mappings
               SET slide_number = ?, graph_name = ?, graph_type = ?,
                   x_column = ?, y_columns_json = ?, chart_config_json = ?,
                   updated_at = CURRENT_TIMESTAMP
               WHERE mapping_id = ?""",
            (slide_number, graph_name, graph_type,
             x_column, json.dumps(y_columns, ensure_ascii=False),
             json.dumps(chart_config or {}, ensure_ascii=False),
             mapping_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_graph_mapping(mapping_id: int):
    conn = _get_conn()
    try:
        conn.execute("DELETE FROM ir_graph_mappings WHERE mapping_id = ?", (mapping_id,))
        conn.commit()
    finally:
        conn.close()


# ── AI指摘操作 ───────────────────────────────────────

def add_suggestion(project_id: int, category: str, severity: str,
                   title: str, detail: str = "", target_element: str = "",
                   suggested_fix: str = "") -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ir_suggestions
               (project_id, category, severity, title, detail, target_element, suggested_fix)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (project_id, category, severity, title, detail, target_element, suggested_fix),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_project_suggestions(project_id: int, include_dismissed: bool = False) -> pd.DataFrame:
    if include_dismissed:
        where = ""
    else:
        where = "AND s.is_dismissed = 0"

    return _query_df(
        f"""SELECT s.*,
                   CASE WHEN lr.rule_id IS NOT NULL THEN 1 ELSE 0 END as has_learning_rule
            FROM ir_suggestions s
            LEFT JOIN ir_learning_rules lr ON s.suggestion_id = lr.suggestion_id
            WHERE s.project_id = ? {where}
            ORDER BY
                CASE s.severity
                    WHEN 'error' THEN 1
                    WHEN 'warning' THEN 2
                    WHEN 'info' THEN 3
                END,
                s.created_at DESC""",
        (project_id,),
    )


def dismiss_suggestion(suggestion_id: int):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE ir_suggestions SET is_dismissed = 1 WHERE suggestion_id = ?",
            (suggestion_id,),
        )
        conn.commit()
    finally:
        conn.close()


# ── 学習ルール操作（F-07/F-08）────────────────────

def add_learning_rule(project_id: int, suggestion_id: int,
                      rule_type: str, rule_detail: str = "") -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ir_learning_rules
               (project_id, suggestion_id, rule_type, rule_detail)
               VALUES (?, ?, ?, ?)""",
            (project_id, suggestion_id, rule_type, rule_detail),
        )
        # 指摘も無視状態にする
        conn.execute(
            "UPDATE ir_suggestions SET is_dismissed = 1 WHERE suggestion_id = ?",
            (suggestion_id,),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_project_learning_rules(project_id: int) -> pd.DataFrame:
    return _query_df(
        """SELECT lr.*, s.category, s.title as suggestion_title
           FROM ir_learning_rules lr
           JOIN ir_suggestions s ON lr.suggestion_id = s.suggestion_id
           WHERE lr.project_id = ?
           ORDER BY lr.created_at DESC""",
        (project_id,),
    )


def is_rule_suppressed(project_id: int, category: str, rule_type: str) -> bool:
    """指定のカテゴリ・ルール種別が学習済みか（資料内のみ有効）"""
    conn = _get_conn()
    try:
        row = conn.execute(
            """SELECT 1 FROM ir_learning_rules lr
               JOIN ir_suggestions s ON lr.suggestion_id = s.suggestion_id
               WHERE lr.project_id = ? AND s.category = ? AND lr.rule_type = ?""",
            (project_id, category, rule_type),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


# ── 通知操作（F-09）──────────────────────────────────

def add_notification(user_id: int, project_id: int | None,
                     notif_type: str, title: str, message: str = ""):
    conn = _get_conn()
    try:
        conn.execute(
            """INSERT INTO ir_notifications
               (user_id, project_id, notif_type, title, message)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, project_id, notif_type, title, message),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_notifications(user_id: int, unread_only: bool = False,
                           limit: int = 50) -> pd.DataFrame:
    where = "AND is_read = 0" if unread_only else ""
    return _query_df(
        f"""SELECT * FROM ir_notifications
            WHERE user_id = ? {where}
            ORDER BY created_at DESC
            LIMIT ?""",
        (user_id, limit),
    )


def get_unread_count(user_id: int) -> int:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM ir_notifications WHERE user_id = ? AND is_read = 0",
            (user_id,),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def mark_notification_read(notification_id: int):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE ir_notifications SET is_read = 1 WHERE notification_id = ?",
            (notification_id,),
        )
        conn.commit()
    finally:
        conn.close()


def mark_all_notifications_read(user_id: int):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE ir_notifications SET is_read = 1 WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


# ── 画像配置操作（F-03）──────────────────────────────

def save_image_placement(project_id: int, upload_id: int,
                         slide_number: int, position_x: float, position_y: float,
                         width: float, height: float,
                         context_label: str = "", ai_confidence: float = 0.0) -> int:
    conn = _get_conn()
    try:
        cursor = conn.execute(
            """INSERT INTO ir_image_placements
               (project_id, upload_id, slide_number, position_x, position_y,
                width, height, context_label, ai_confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (project_id, upload_id, slide_number, position_x, position_y,
             width, height, context_label, ai_confidence),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_project_image_placements(project_id: int) -> pd.DataFrame:
    return _query_df(
        """SELECT ip.*, u.original_name
           FROM ir_image_placements ip
           JOIN ir_uploads u ON ip.upload_id = u.upload_id
           WHERE ip.project_id = ?
           ORDER BY ip.slide_number, ip.placement_id""",
        (project_id,),
    )
