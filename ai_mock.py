# -*- coding: utf-8 -*-
"""
Insight Arc — モック AI エンジン

実際のAI APIが接続されるまでの間、ルールベースで
IR資料の校正指摘・画像配置提案・トレンド分析を行う。
後からClaude API / OpenAI API等に差し替え可能な設計。
"""

import random
from datetime import datetime
from typing import Optional

import pandas as pd


class MockAIEngine:
    """モックAIエンジン - ルールベースの分析・指摘生成"""

    # ── F-05: AI校正ルール定義 ────────────────────────

    PROOFREADING_RULES = [
        {
            "category": "数値整合性",
            "rule_type": "numeric_consistency",
            "check": "前年同期比の計算が正しいか",
            "severity": "error",
        },
        {
            "category": "数値整合性",
            "rule_type": "numeric_range",
            "check": "異常値の検出（前期比±50%以上の変動）",
            "severity": "warning",
        },
        {
            "category": "表現チェック",
            "rule_type": "expression_positive",
            "check": "過度にポジティブな表現がないか",
            "severity": "info",
        },
        {
            "category": "表現チェック",
            "rule_type": "expression_vague",
            "check": "曖昧な表現（「概ね」「若干」等）が多用されていないか",
            "severity": "info",
        },
        {
            "category": "グラフ整合性",
            "rule_type": "graph_data_match",
            "check": "グラフの数値とテキスト記載の数値が一致しているか",
            "severity": "error",
        },
        {
            "category": "KPI整合性",
            "rule_type": "kpi_coverage",
            "check": "主要KPIが全て記載されているか",
            "severity": "warning",
        },
        {
            "category": "トレンド分析",
            "rule_type": "trend_anomaly",
            "check": "トレンドの異常変動に対する説明が記載されているか",
            "severity": "warning",
        },
        {
            "category": "フォーマット",
            "rule_type": "format_consistency",
            "check": "数値のフォーマット（単位、桁区切り）が統一されているか",
            "severity": "info",
        },
    ]

    def analyze_financial_data(self, data: pd.DataFrame,
                               suppressed_rules: list[str] = None) -> list[dict]:
        """
        財務データを分析し、指摘リストを生成する（モック）

        Returns:
            list[dict]: 各指摘は {category, severity, title, detail,
                         target_element, suggested_fix, rule_type} を含む
        """
        suppressed = set(suppressed_rules or [])
        suggestions = []

        if data.empty:
            return suggestions

        # 数値データがある場合の分析
        numeric_cols = data.select_dtypes(include="number").columns.tolist()

        for col in numeric_cols:
            col_data = data[col].dropna()
            if len(col_data) < 2:
                continue

            # 前期比チェック
            if "numeric_consistency" not in suppressed:
                for i in range(1, len(col_data)):
                    prev = col_data.iloc[i - 1]
                    curr = col_data.iloc[i]
                    if prev != 0:
                        change_pct = abs((curr - prev) / prev) * 100
                        if change_pct > 50:
                            suggestions.append({
                                "category": "数値整合性",
                                "severity": "warning",
                                "title": f"「{col}」に大幅な変動を検出",
                                "detail": f"前期比 {change_pct:.1f}% の変動があります。投資家への説明が必要な可能性があります。",
                                "target_element": col,
                                "suggested_fix": f"変動要因の説明を追記することを推奨します。",
                                "rule_type": "numeric_range",
                            })
                            break  # 1列につき1指摘まで

            # トレンド異常チェック
            if "trend_anomaly" not in suppressed and len(col_data) >= 4:
                trend = col_data.diff().dropna()
                if len(trend) >= 3:
                    recent_direction = trend.iloc[-1]
                    prev_direction = trend.iloc[-2]
                    if (recent_direction > 0) != (prev_direction > 0):
                        suggestions.append({
                            "category": "トレンド分析",
                            "severity": "info",
                            "title": f"「{col}」のトレンド転換を検出",
                            "detail": f"直近でトレンドの方向が変化しています。重要な転換点の可能性があります。",
                            "target_element": col,
                            "suggested_fix": "トレンド変化の背景・要因の説明を追加することを推奨します。",
                            "rule_type": "trend_anomaly",
                        })

        # フォーマット統一チェック（常に追加）
        if "format_consistency" not in suppressed and len(numeric_cols) > 0:
            suggestions.append({
                "category": "フォーマット",
                "severity": "info",
                "title": "数値フォーマットの統一確認",
                "detail": "全てのKPI数値が同一の単位・桁区切りで表記されているか確認してください。",
                "target_element": "全体",
                "suggested_fix": "金額は「百万円」または「億円」で統一し、桁区切りを付けてください。",
                "rule_type": "format_consistency",
            })

        # KPIカバレッジチェック
        if "kpi_coverage" not in suppressed:
            expected_kpis = {"売上高", "営業利益", "純利益", "総資産", "営業CF"}
            found_kpis = set()
            for col in data.columns:
                for kpi in expected_kpis:
                    if kpi in str(col):
                        found_kpis.add(kpi)
            missing = expected_kpis - found_kpis
            if missing:
                suggestions.append({
                    "category": "KPI整合性",
                    "severity": "warning",
                    "title": "主要KPIの記載漏れの可能性",
                    "detail": f"以下のKPIが見当たりません: {', '.join(missing)}",
                    "target_element": "KPIセクション",
                    "suggested_fix": f"不足しているKPI（{', '.join(missing)}）の追加を検討してください。",
                    "rule_type": "kpi_coverage",
                })

        return suggestions

    def analyze_text_content(self, text: str,
                              suppressed_rules: list[str] = None) -> list[dict]:
        """テキスト内容を分析し指摘を生成（モック）"""
        suppressed = set(suppressed_rules or [])
        suggestions = []

        if not text:
            return suggestions

        # ポジティブ表現チェック
        if "expression_positive" not in suppressed:
            positive_words = ["飛躍的", "大幅に改善", "過去最高", "急成長", "目覚ましい"]
            found = [w for w in positive_words if w in text]
            if len(found) >= 2:
                suggestions.append({
                    "category": "表現チェック",
                    "severity": "info",
                    "title": "ポジティブ表現の多用に注意",
                    "detail": f"以下のポジティブ表現が検出されました: {', '.join(found)}。投資家の信頼性確保の観点から、客観的なデータに基づく表現を推奨します。",
                    "target_element": "テキスト全体",
                    "suggested_fix": "具体的な数値や比較データと共に記載することを推奨します。",
                    "rule_type": "expression_positive",
                })

        # 曖昧表現チェック
        if "expression_vague" not in suppressed:
            vague_words = ["概ね", "若干", "一定の", "ある程度", "おおむね"]
            found = [w for w in vague_words if w in text]
            if found:
                suggestions.append({
                    "category": "表現チェック",
                    "severity": "info",
                    "title": "曖昧な表現の検出",
                    "detail": f"以下の曖昧な表現が検出されました: {', '.join(found)}。具体的な数値への置き換えを検討してください。",
                    "target_element": "テキスト全体",
                    "suggested_fix": "定量的なデータ（%、金額等）に置き換えることで、投資家への訴求力が向上します。",
                    "rule_type": "expression_vague",
                })

        return suggestions

    def suggest_image_placement(self, image_name: str, image_bytes: bytes,
                                slide_count: int = 10) -> dict:
        """
        画像の自動配置を提案する（モック）

        実際のAI実装では画像認識を行い、内容に基づいて
        最適なスライド位置を提案する。
        """
        # モック: ファイル名やサイズから推定
        name_lower = image_name.lower()

        if any(w in name_lower for w in ["chart", "graph", "グラフ", "推移"]):
            context = "業績推移・グラフセクション"
            slide = min(3, slide_count)
            confidence = 0.85
        elif any(w in name_lower for w in ["photo", "写真", "building", "社屋"]):
            context = "会社概要・施設紹介セクション"
            slide = 1
            confidence = 0.80
        elif any(w in name_lower for w in ["product", "製品", "service", "サービス"]):
            context = "事業内容・製品紹介セクション"
            slide = min(4, slide_count)
            confidence = 0.75
        elif any(w in name_lower for w in ["team", "人", "社員", "member"]):
            context = "経営陣・チーム紹介セクション"
            slide = min(8, slide_count)
            confidence = 0.70
        else:
            context = "補足資料セクション"
            slide = min(slide_count, max(1, slide_count - 2))
            confidence = 0.50

        return {
            "slide_number": slide,
            "position_x": 1.5,
            "position_y": 2.0,
            "width": 7.0,
            "height": 5.0,
            "context_label": context,
            "ai_confidence": confidence,
        }

    def generate_trend_analysis(self, data: pd.DataFrame,
                                 period_years: int = 5) -> dict:
        """
        長期トレンド分析を生成する（F-04, モック）

        Returns:
            dict: {summary, highlights, risks, outlook}
        """
        if data.empty:
            return {
                "summary": "分析対象のデータがありません。",
                "highlights": [],
                "risks": [],
                "outlook": "",
            }

        numeric_cols = data.select_dtypes(include="number").columns.tolist()
        highlights = []
        risks = []

        for col in numeric_cols[:5]:  # 上位5指標を分析
            col_data = data[col].dropna()
            if len(col_data) < 2:
                continue

            first_val = col_data.iloc[0]
            last_val = col_data.iloc[-1]

            if first_val and first_val != 0:
                total_change = ((last_val - first_val) / abs(first_val)) * 100

                if total_change > 20:
                    highlights.append(
                        f"「{col}」は分析期間中に {total_change:.1f}% 成長しています。"
                    )
                elif total_change < -20:
                    risks.append(
                        f"「{col}」は分析期間中に {abs(total_change):.1f}% 減少しています。"
                    )

        summary = f"直近{period_years}年間のデータを分析しました。"
        if highlights:
            summary += f" {len(highlights)}件の好調指標を検出しました。"
        if risks:
            summary += f" {len(risks)}件の注意指標を検出しました。"

        outlook = "今後の動向については、直近の四半期決算の推移を注視することを推奨します。"

        return {
            "summary": summary,
            "highlights": highlights,
            "risks": risks,
            "outlook": outlook,
        }
