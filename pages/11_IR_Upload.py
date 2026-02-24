# -*- coding: utf-8 -*-
"""
Insight Arc — F-01 マルチインプット（ファイルアップロード）

PowerPoint、Excel、画像ファイルの同時アップロードに対応。
F-03: 画像自動配置（モックAI）もここで実行。
"""

import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import auth_helper as auth
import ir_db_helper as ir_db
from ai_mock import MockAIEngine

st.set_page_config(
    page_title="ファイルアップロード | Insight Arc",
    page_icon="📁",
    layout="wide",
)

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
    st.warning("先にIRダッシュボードでプロジェクトを作成してください。")
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
    "プロジェクトを選択",
    list(project_options.keys()),
    index=default_idx,
    key="upload_project_select",
)
project_id = project_options[selected_label]
project = ir_db.get_project(project_id)

st.title(f"ファイルアップロード — {project['title']}")
st.caption("F-01: PowerPoint / Excel / 画像の同時アップロード対応")

# ── ファイルタイプ判定 ────────────────────────────────

ALLOWED_TYPES = {
    "pptx": {"extensions": [".pptx", ".ppt"], "label": "PowerPoint", "icon": "📊"},
    "excel": {"extensions": [".xlsx", ".xls", ".csv"], "label": "Excel/CSV", "icon": "📈"},
    "image": {"extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp"], "label": "画像", "icon": "🖼️"},
}


def detect_file_type(filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    for ftype, info in ALLOWED_TYPES.items():
        if ext in info["extensions"]:
            return ftype
    return None


# ── アップロードUI ───────────────────────────────────

st.markdown("### ファイルをアップロード")
st.info("PowerPoint (.pptx)、Excel (.xlsx/.csv)、画像 (.jpg/.png) を一度に複数アップロードできます。")

uploaded_files = st.file_uploader(
    "ファイルを選択（複数可）",
    type=["pptx", "ppt", "xlsx", "xls", "csv", "jpg", "jpeg", "png", "gif", "bmp"],
    accept_multiple_files=True,
    key="multi_upload",
)

if uploaded_files:
    st.markdown("#### アップロード確認")

    upload_summary = {"pptx": [], "excel": [], "image": [], "unknown": []}
    for f in uploaded_files:
        ftype = detect_file_type(f.name)
        if ftype:
            upload_summary[ftype].append(f)
        else:
            upload_summary["unknown"].append(f)

    # サマリー表示
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("PowerPoint", f"{len(upload_summary['pptx'])} ファイル")
    with col2:
        st.metric("Excel/CSV", f"{len(upload_summary['excel'])} ファイル")
    with col3:
        st.metric("画像", f"{len(upload_summary['image'])} ファイル")

    if upload_summary["unknown"]:
        st.warning(f"未対応のファイル形式: {', '.join(f.name for f in upload_summary['unknown'])}")

    # アップロード実行ボタン
    if st.button("アップロード実行", type="primary", use_container_width=True):
        progress = st.progress(0, text="アップロード中...")
        total = sum(len(v) for v in upload_summary.values()) - len(upload_summary["unknown"])
        done = 0

        for ftype in ["pptx", "excel", "image"]:
            for f in upload_summary[ftype]:
                file_bytes = f.read()

                # メタデータ収集
                metadata = {"original_size": len(file_bytes)}

                # Excelの場合、シート名とデータを解析
                if ftype == "excel":
                    try:
                        if f.name.endswith(".csv"):
                            df = pd.read_csv(io.BytesIO(file_bytes))
                            metadata["sheets"] = ["Sheet1"]
                            metadata["row_count"] = len(df)
                            metadata["columns"] = list(df.columns)
                        else:
                            xls = pd.ExcelFile(io.BytesIO(file_bytes))
                            metadata["sheets"] = xls.sheet_names
                            # 最初のシートの情報
                            df = pd.read_excel(xls, sheet_name=0)
                            metadata["row_count"] = len(df)
                            metadata["columns"] = list(df.columns)
                    except Exception as e:
                        metadata["parse_error"] = str(e)

                # PowerPointの場合
                if ftype == "pptx":
                    metadata["file_format"] = "PowerPoint"

                # ファイル保存
                upload_id = ir_db.save_upload(
                    project_id=project_id,
                    file_type=ftype,
                    original_name=f.name,
                    file_bytes=file_bytes,
                    metadata=metadata,
                )

                # F-03: 画像の場合、AI自動配置提案を生成
                if ftype == "image":
                    placement = ai.suggest_image_placement(
                        f.name, file_bytes, slide_count=10
                    )
                    ir_db.save_image_placement(
                        project_id=project_id,
                        upload_id=upload_id,
                        **placement,
                    )

                # Excelの場合、データ同期用にパース
                if ftype == "excel" and "parse_error" not in metadata:
                    try:
                        if f.name.endswith(".csv"):
                            df = pd.read_csv(io.BytesIO(file_bytes))
                            ir_db.save_excel_data(
                                project_id=project_id,
                                upload_id=upload_id,
                                sheet_name="Sheet1",
                                data=df.to_dict(orient="records"),
                                label=f.name,
                                data_type="kpi",
                            )
                        else:
                            xls = pd.ExcelFile(io.BytesIO(file_bytes))
                            for sheet in xls.sheet_names:
                                sheet_df = pd.read_excel(xls, sheet_name=sheet)
                                ir_db.save_excel_data(
                                    project_id=project_id,
                                    upload_id=upload_id,
                                    sheet_name=sheet,
                                    data=sheet_df.to_dict(orient="records"),
                                    label=f"{f.name} / {sheet}",
                                    data_type="kpi",
                                )
                    except Exception:
                        pass

                done += 1
                progress.progress(done / max(total, 1), text=f"アップロード中... ({done}/{total})")

        progress.progress(1.0, text="完了")

        # 通知を作成
        ir_db.add_notification(
            user_id, project_id, "upload_complete",
            "ファイルアップロード完了",
            f"{total}件のファイルがアップロードされました。",
        )

        st.success(f"{total} ファイルのアップロードが完了しました。")
        st.rerun()

# ── アップロード済みファイル一覧 ──────────────────────

st.divider()
st.markdown("### アップロード済みファイル")

uploads = ir_db.get_project_uploads(project_id)

if uploads.empty:
    st.info("まだファイルがアップロードされていません。")
else:
    # タイプ別に表示
    for ftype, info in ALLOWED_TYPES.items():
        type_files = uploads[uploads["file_type"] == ftype]
        if type_files.empty:
            continue

        st.markdown(f"#### {info['icon']} {info['label']}（{len(type_files)} ファイル）")

        for _, file_row in type_files.iterrows():
            col_name, col_size, col_date, col_del = st.columns([3, 1, 1, 1])

            with col_name:
                st.markdown(f"**{file_row['original_name']}**")

                # Excelの場合、メタデータ表示
                if ftype == "excel" and file_row["metadata_json"]:
                    try:
                        meta = json.loads(file_row["metadata_json"])
                        if "sheets" in meta:
                            st.caption(
                                f"シート: {', '.join(meta['sheets'])} | "
                                f"行数: {meta.get('row_count', '?')}"
                            )
                    except Exception:
                        pass

                # 画像の場合、配置提案を表示
                if ftype == "image":
                    placements = ir_db.get_project_image_placements(project_id)
                    img_placements = placements[placements["upload_id"] == file_row["upload_id"]]
                    if not img_placements.empty:
                        p = img_placements.iloc[0]
                        st.caption(
                            f"AI配置提案: スライド{p['slide_number']} / "
                            f"{p['context_label']} "
                            f"(信頼度: {p['ai_confidence']:.0%})"
                        )

            with col_size:
                size_kb = (file_row["file_size"] or 0) / 1024
                if size_kb > 1024:
                    st.caption(f"{size_kb / 1024:.1f} MB")
                else:
                    st.caption(f"{size_kb:.0f} KB")

            with col_date:
                st.caption(file_row["uploaded_at"][:16] if file_row["uploaded_at"] else "")

            with col_del:
                if st.button("削除", key=f"del_{file_row['upload_id']}"):
                    ir_db.delete_upload(file_row["upload_id"])
                    st.rerun()

        st.divider()

# ── 画像自動配置プレビュー（F-03）────────────────────

placements = ir_db.get_project_image_placements(project_id)
if not placements.empty:
    st.markdown("### F-03: 画像自動配置プレビュー")
    st.caption("AIが画像の内容を解析し、資料内の適切な位置への配置を提案します。")

    for _, p in placements.iterrows():
        col_img, col_info = st.columns([1, 2])

        with col_img:
            # 画像プレビュー
            stored_path = Path(
                uploads[uploads["upload_id"] == p["upload_id"]].iloc[0]["stored_path"]
            ) if not uploads[uploads["upload_id"] == p["upload_id"]].empty else None

            if stored_path and stored_path.exists() and stored_path.suffix.lower() in [".jpg", ".jpeg", ".png", ".gif", ".bmp"]:
                st.image(str(stored_path), width=200)
            else:
                st.caption(f"[{p['original_name']}]")

        with col_info:
            confidence_color = (
                "#43a047" if p["ai_confidence"] >= 0.7
                else "#f9a825" if p["ai_confidence"] >= 0.5
                else "#e53935"
            )
            st.markdown(f"""
            | 項目 | 値 |
            |---|---|
            | 配置先スライド | **スライド {p['slide_number']}** |
            | コンテキスト | {p['context_label']} |
            | AI信頼度 | <span style="color:{confidence_color};font-weight:bold">{p['ai_confidence']:.0%}</span> |
            | 位置 | X={p['position_x']}, Y={p['position_y']} |
            | サイズ | W={p['width']} x H={p['height']} |
            """, unsafe_allow_html=True)

# ── 次のステップへ ───────────────────────────────────

st.divider()
col_back, col_next = st.columns(2)
with col_back:
    st.link_button("ダッシュボードに戻る", "/IR_Dashboard", use_container_width=True)
with col_next:
    st.link_button(
        "データ分析・グラフ同期へ進む →",
        f"/IR_Editor?project_id={project_id}",
        type="primary",
        use_container_width=True,
    )
