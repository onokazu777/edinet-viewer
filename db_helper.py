# -*- coding: utf-8 -*-
"""
EDINET Viewer — DB ヘルパー

SQLite データベースからデータを取得し、Streamlit の
@st.cache_data でキャッシュして返すユーティリティ群。
"""

import sqlite3
import pandas as pd
import streamlit as st
from pathlib import Path
from typing import Optional

# ── DB パス ──────────────────────────────────────────

DB_PATH = Path(__file__).parent / "data" / "edinet_data.sqlite3"


def get_connection() -> sqlite3.Connection:
    """SQLite 接続を取得（読み取り専用）"""
    if not DB_PATH.exists():
        st.error(f"データベースが見つかりません: {DB_PATH}")
        st.stop()
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _query_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    """SQL を実行して DataFrame で返す"""
    conn = get_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return df
    finally:
        conn.close()


# ── 統計情報 ─────────────────────────────────────────

@st.cache_data(ttl=3600)
def get_db_stats() -> dict:
    """データベースの統計情報を取得"""
    conn = get_connection()
    try:
        stats = {}
        # 書類数
        stats["total_docs"] = conn.execute(
            "SELECT COUNT(*) FROM documents"
        ).fetchone()[0]
        # 企業数（ユニークな証券コード）
        stats["total_companies"] = conn.execute(
            "SELECT COUNT(DISTINCT sec_code) FROM documents WHERE sec_code IS NOT NULL AND sec_code != ''"
        ).fetchone()[0]
        # 解析済み
        try:
            stats["parsed_docs"] = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE parse_status = 1"
            ).fetchone()[0]
        except Exception:
            stats["parsed_docs"] = 0
        # DL 済み
        try:
            stats["downloaded_docs"] = conn.execute(
                "SELECT COUNT(*) FROM documents WHERE dl_status > 0"
            ).fetchone()[0]
        except Exception:
            stats["downloaded_docs"] = 0
        # 財務レコード数（key_financials テーブル or financials テーブル）
        try:
            stats["financial_records"] = conn.execute(
                "SELECT COUNT(*) FROM key_financials"
            ).fetchone()[0]
        except Exception:
            try:
                stats["financial_records"] = conn.execute(
                    "SELECT COUNT(*) FROM financials"
                ).fetchone()[0]
            except Exception:
                stats["financial_records"] = 0
        # テキストブロック数
        try:
            stats["text_blocks"] = conn.execute(
                "SELECT COUNT(*) FROM text_blocks"
            ).fetchone()[0]
        except Exception:
            stats["text_blocks"] = 0
        # 期間
        row = conn.execute(
            "SELECT MIN(file_date) as min_date, MAX(file_date) as max_date FROM documents"
        ).fetchone()
        stats["date_from"] = row[0] or ""
        stats["date_to"] = row[1] or ""
        # 書類種別ごとの件数
        rows = conn.execute("""
            SELECT doc_type_code, COUNT(*) as cnt FROM documents
            GROUP BY doc_type_code ORDER BY cnt DESC
        """).fetchall()
        stats["doc_type_counts"] = {r[0]: r[1] for r in rows}
        return stats
    finally:
        conn.close()


# ── 企業一覧・検索 ──────────────────────────────────

@st.cache_data(ttl=3600)
def get_company_list() -> pd.DataFrame:
    """全企業の証券コード + 名前リストを取得"""
    return _query_df("""
        SELECT DISTINCT
            sec_code,
            filer_name,
            COUNT(*) as doc_count,
            MAX(file_date) as latest_date
        FROM documents
        WHERE sec_code IS NOT NULL AND sec_code != ''
        GROUP BY sec_code, filer_name
        ORDER BY sec_code
    """)


def search_companies(keyword: str) -> pd.DataFrame:
    """企業名 or 証券コードで部分一致検索"""
    if not keyword.strip():
        return pd.DataFrame()
    like = f"%{keyword.strip()}%"
    return _query_df("""
        SELECT DISTINCT
            sec_code,
            filer_name,
            COUNT(*) as doc_count,
            MAX(file_date) as latest_date
        FROM documents
        WHERE sec_code IS NOT NULL AND sec_code != ''
          AND (sec_code LIKE ? OR filer_name LIKE ?)
        GROUP BY sec_code, filer_name
        ORDER BY sec_code
    """, (like, like))


# ── 企業詳細 ────────────────────────────────────────

DOC_TYPE_NAMES = {
    "120": "有価証券報告書",
    "130": "訂正有価証券報告書",
    "140": "四半期報告書",
    "150": "訂正四半期報告書",
    "160": "半期報告書",
    "170": "訂正半期報告書",
    "060": "大量保有報告書",
    "070": "訂正大量保有報告書",
}


def get_company_documents(sec_code: str) -> pd.DataFrame:
    """指定企業の書類一覧を取得"""
    return _query_df("""
        SELECT
            doc_id, filer_name, doc_type_code, doc_description,
            period_start, period_end, submit_date, file_date
        FROM documents
        WHERE sec_code = ?
        ORDER BY file_date DESC
    """, (sec_code,))


def get_key_financials(sec_code: str) -> pd.DataFrame:
    """企業の主要財務指標を期別に取得（v_key_financials ビュー使用）"""
    return _query_df("""
        SELECT * FROM v_key_financials
        WHERE sec_code = ?
        ORDER BY period_end DESC
    """, (sec_code,))


def get_financial_details(sec_code: str, is_consolidated: int = 1) -> pd.DataFrame:
    """企業の全財務データを取得（financials テーブルがあれば詳細、なければ集約データ）"""
    try:
        return _query_df("""
            SELECT
                f.doc_id, f.period_start, f.period_end,
                f.account_element, f.account_label,
                f.context, f.unit, f.value,
                f.is_consolidated, f.statement_type
            FROM financials f
            WHERE f.sec_code = ? AND f.is_consolidated = ?
            ORDER BY f.period_end DESC, f.statement_type, f.account_element
        """, (sec_code, is_consolidated))
    except Exception:
        # financials テーブルが無い場合（最小DB）は空を返す
        return pd.DataFrame()


def get_company_text_blocks(sec_code: str) -> pd.DataFrame:
    """企業のテキストブロックを取得"""
    return _query_df("""
        SELECT
            doc_id, sec_code, filer_name,
            period_start, period_end,
            element_name, section_label, context,
            text_content
        FROM text_blocks
        WHERE sec_code = ?
        ORDER BY period_end DESC, element_name
    """, (sec_code,))


def get_company_info(sec_code: str) -> dict:
    """企業の基本情報を取得"""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT
                sec_code, filer_name,
                COUNT(*) as doc_count,
                MIN(file_date) as first_date,
                MAX(file_date) as latest_date
            FROM documents
            WHERE sec_code = ?
            GROUP BY sec_code
        """, (sec_code,)).fetchone()
        if row:
            return dict(row)
        return {}
    finally:
        conn.close()


# ── 企業比較 ────────────────────────────────────────

def get_multi_company_financials(sec_codes: list[str]) -> pd.DataFrame:
    """複数企業の主要財務指標を取得"""
    if not sec_codes:
        return pd.DataFrame()
    placeholders = ",".join("?" * len(sec_codes))
    return _query_df(f"""
        SELECT * FROM v_key_financials
        WHERE sec_code IN ({placeholders})
        ORDER BY sec_code, period_end DESC
    """, tuple(sec_codes))


# ── スクリーニング ──────────────────────────────────

def get_screening_data() -> pd.DataFrame:
    """
    スクリーニング用に全企業の最新期の主要財務指標を取得。
    各企業の最新の期末データのみを返す。
    """
    return _query_df("""
        WITH latest AS (
            SELECT sec_code, MAX(period_end) as max_period
            FROM v_key_financials
            WHERE is_consolidated = 1
            GROUP BY sec_code
        )
        SELECT v.*
        FROM v_key_financials v
        INNER JOIN latest l
            ON v.sec_code = l.sec_code
            AND v.period_end = l.max_period
        WHERE v.is_consolidated = 1
        ORDER BY v.sec_code
    """)


# ── テキストブロック ────────────────────────────────

def get_text_block_sections() -> list[str]:
    """利用可能なテキストブロックセクション名のリストを取得"""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT DISTINCT section_label
            FROM text_blocks
            WHERE section_label IS NOT NULL AND section_label != ''
            ORDER BY section_label
        """).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def search_text_blocks(
    sec_code: Optional[str] = None,
    section_label: Optional[str] = None,
    keyword: Optional[str] = None,
    period_end: Optional[str] = None,
    limit: int = 50,
) -> pd.DataFrame:
    """テキストブロックを検索"""
    conditions = ["1=1"]
    params = []

    if sec_code:
        conditions.append("sec_code = ?")
        params.append(sec_code)
    if section_label:
        conditions.append("section_label = ?")
        params.append(section_label)
    if keyword:
        conditions.append("text_content LIKE ?")
        params.append(f"%{keyword}%")
    if period_end:
        conditions.append("period_end = ?")
        params.append(period_end)

    where = " AND ".join(conditions)

    return _query_df(f"""
        SELECT
            doc_id, sec_code, filer_name,
            period_start, period_end,
            element_name, section_label,
            text_content
        FROM text_blocks
        WHERE {where}
        ORDER BY period_end DESC, sec_code
        LIMIT ?
    """, tuple(params) + (limit,))


# ── 最近の提出書類 ──────────────────────────────────

@st.cache_data(ttl=600)
def get_recent_documents(limit: int = 30) -> pd.DataFrame:
    """最近提出された書類リストを取得"""
    return _query_df("""
        SELECT
            doc_id, sec_code, filer_name,
            doc_type_code, doc_description,
            period_start, period_end,
            submit_date, file_date
        FROM documents
        WHERE sec_code IS NOT NULL AND sec_code != ''
        ORDER BY file_date DESC, submit_date DESC
        LIMIT ?
    """, (limit,))
