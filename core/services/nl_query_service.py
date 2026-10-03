"""Natural Language Dashboard Querying Service (Text-to-SQL & Semantic Analytics).

Translates natural language questions into safe, read-only SQL queries on audit data,
with automated chart suggestion and robust fallback rule matching.
"""

import json
import logging
import re
import time
from typing import Any

from sqlalchemy import text

from core.infra.database import engine

logger = logging.getLogger(__name__)

FORBIDDEN_SQL_KEYWORDS = {
    "drop",
    "delete",
    "update",
    "insert",
    "alter",
    "truncate",
    "create",
    "pragma",
    "exec",
    "execute",
    "attach",
    "detach",
    "grant",
    "revoke",
    "vacuum",
    "reindex",
}

ALLOWED_TABLES = {"auditreport", "audit_core_members"}

SYSTEM_PROMPT = """You are WARDEN SQL Copilot, an expert database assistant for WARDEN autonomous code governance engine.
Your task is to translate user natural language questions into a single SQLite-compatible SELECT query.

Database Schema:
1. Table `auditreport`:
   - id (INTEGER, PRIMARY KEY)
   - repo_path (TEXT): Path or name of the audited repository
   - total_score (INTEGER): Overall quality score (0-100)
   - grade (TEXT): Letter grade (A, B, C, D, F)
   - profile_signature (TEXT): Project archetype (e.g. FastAPI, Django, CLI)
   - layer1_score (INTEGER): Mechanical analysis score (0-100)
   - layer2_score (INTEGER): LLM rubric score (0-100, -1 if unmeasured)
   - group_security (REAL): Security & Supply Chain score (0-100)
   - group_code_health (REAL): Code Health & Testing score (0-100)
   - group_structural (REAL): Structural & Architecture score (0-100)
   - group_resilience (REAL): Resilience & Performance score (0-100)
   - group_dev_hygiene (REAL): DevOps & Developer Hygiene score (0-100)
   - is_milestone (BOOLEAN): 1 if marked as reference milestone
   - milestone_label (TEXT): Optional milestone label (e.g. 'v1.0-baseline')
   - created_at (TIMESTAMP): Audit timestamp

2. Table `audit_core_members`:
   - id (INTEGER, PRIMARY KEY)
   - report_id (INTEGER): Foreign key referencing auditreport.id
   - group_key (TEXT): E.g. 'security_supply_chain', 'code_health_test'
   - member_key (TEXT): E.g. 'semgrep_security', 'cyclomatic_complexity'
   - member_label (TEXT): Human readable label
   - score (REAL): Member score (0-100)

RULES:
- Return ONLY a JSON object with keys: "sql", "explanation", "chart_type".
- "chart_type" must be one of: "bar_chart", "line_chart", "stat_card", "table".
- Only SELECT queries are allowed. NEVER use INSERT, UPDATE, DELETE, DROP, ALTER, PRAGMA.
- Always include a LIMIT clause (max 100).
- Do not wrap in markdown quotes if possible, or use standard json block.
"""


class NaturalLanguageQueryService:
    """Translates user natural language questions into safe read-only SQL queries."""

    def validate_and_sanitize_sql(self, sql: str) -> str:
        """Validates that query is strictly a read-only SELECT statement adhering to guardrails."""
        cleaned = sql.strip().strip(";")
        if not cleaned:
            raise ValueError("Boş SQL sorgusu yürütülemez.")

        # Disallow multiple stacked statements (SQL injection / chaining)
        # Check for unquoted semicolons
        in_single_quote = False
        in_double_quote = False
        for ch in cleaned:
            if ch == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif ch == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif ch == ";" and not in_single_quote and not in_double_quote:
                raise ValueError("Güvenlik İhlali: Çoklu SQL ifadesi (stacked query) yürütmek yasaktır.")

        # Tokenize words
        tokens = re.findall(r"\b[A-Za-z_]+\b", cleaned.lower())
        if not tokens:
            raise ValueError("Geçersiz SQL sözdizimi.")

        # Must start with SELECT or WITH
        if tokens[0] not in ("select", "with"):
            raise ValueError(f"Güvenlik İhlali: Yalnızca SELECT sorguları kabul edilir (Başlangıç: '{tokens[0]}').")

        # Check for forbidden keywords
        for tok in tokens:
            if tok in FORBIDDEN_SQL_KEYWORDS:
                raise ValueError(f"Güvenlik İhlali: İzin verilmeyen SQL komutu tespit edildi: '{tok}'.")

        # Table whitelist check
        found_allowed = False
        for tok in tokens:
            if tok in ALLOWED_TABLES:
                found_allowed = True
                break
        if not found_allowed:
            raise ValueError("Güvenlik İhlali: Yalnızca WARDEN audit tabloları ('auditreport', 'audit_core_members') sorgulanabilir.")

        # Enforce maximum LIMIT 100
        lower_query = cleaned.lower()
        if "limit" not in lower_query:
            cleaned = f"{cleaned} LIMIT 100"
        else:
            # If limit exists, verify it doesn't exceed 100
            match = re.search(r"\blimit\s+(\d+)", lower_query)
            if match:
                val = int(match.group(1))
                if val > 100:
                    cleaned = re.sub(r"\blimit\s+\d+", "LIMIT 100", cleaned, flags=re.IGNORECASE)

        return cleaned

    def _fallback_rule_based_sql(self, query: str) -> tuple[str, str, str]:
        """Provides intelligent heuristic matching when LLM is unavailable or unconfigured."""
        q = query.lower()

        # 1. Lowest / worst score
        if any(w in q for w in ("en düşük", "en kötü", "lowest", "worst", "düşük skor", "kötü")):
            sql = (
                "SELECT repo_path, total_score, grade, layer1_score, layer2_score "
                "FROM auditreport ORDER BY total_score ASC LIMIT 5"
            )
            return sql, "Toplam kalite skoru en düşük olan 5 denetim raporu listelenmiştir.", "bar_chart"

        # 2. Highest / best score
        if any(w in q for w in ("en yüksek", "en iyi", "highest", "best", "en başarılı", "en kaliteli")):
            sql = (
                "SELECT repo_path, total_score, grade, layer1_score, layer2_score "
                "FROM auditreport ORDER BY total_score DESC LIMIT 5"
            )
            return sql, "Toplam kalite skoru en yüksek olan 5 denetim raporu listelenmiştir.", "bar_chart"

        # 3. Grade distribution
        if any(w in q for w in ("not dağılımı", "grade distribution", "harf notu", "kaç tane a", "notlar", "dağılım")):
            sql = (
                "SELECT grade, COUNT(*) as audit_count, ROUND(AVG(total_score), 1) as avg_score "
                "FROM auditreport GROUP BY grade ORDER BY audit_count DESC LIMIT 10"
            )
            return sql, "Denetimlerin harf notlarına göre dağılımı ve ortalama skorları.", "bar_chart"

        # 4. Security focus
        if any(w in q for w in ("güvenlik", "security", "zafiyet", "vulnerability", "secret", "sır")):
            sql = (
                "SELECT repo_path, group_security, total_score, grade "
                "FROM auditreport WHERE group_security IS NOT NULL ORDER BY group_security ASC LIMIT 5"
            )
            return sql, "Güvenlik & Tedarik Zinciri puanı en düşük olan denetimler listelenmiştir.", "bar_chart"

        # 5. Architecture & Circular imports
        if any(w in q for w in ("mimari", "döngü", "circular", "structural", "yapısal")):
            sql = (
                "SELECT repo_path, group_structural, total_score, grade "
                "FROM auditreport WHERE group_structural IS NOT NULL ORDER BY group_structural ASC LIMIT 5"
            )
            return sql, "Mimari & Yapısal Sağlık puanı en düşük olan denetimler listelenmiştir.", "bar_chart"

        # 6. Overall average & statistics
        if any(w in q for w in ("ortalama", "average", "genel durum", "özet", "stats", "istatistik")):
            sql = (
                "SELECT ROUND(AVG(total_score), 1) as average_score, COUNT(*) as total_audits, "
                "MAX(total_score) as highest_score, MIN(total_score) as lowest_score "
                "FROM auditreport"
            )
            return sql, "Tüm sistemdeki denetimlerin genel istatistiksel kalite özeti.", "stat_card"

        # 7. Trend over time
        if any(w in q for w in ("trend", "zaman", "gelişim", "tarih", "günlük", "timeline")):
            sql = (
                "SELECT date(created_at) as audit_date, ROUND(AVG(total_score), 1) as avg_score, COUNT(*) as audits "
                "FROM auditreport GROUP BY audit_date ORDER BY audit_date ASC LIMIT 30"
            )
            return sql, "Tarihe göre denetim skorlarındaki değişim trendi.", "line_chart"

        # 8. Milestone benchmarks
        if any(w in q for w in ("milestone", "baseline", "referans")):
            sql = (
                "SELECT id, repo_path, total_score, grade, milestone_label, created_at "
                "FROM auditreport WHERE is_milestone = 1 ORDER BY id DESC LIMIT 20"
            )
            return sql, "Milestone (referans baseline) olarak işaretlenmiş denetimler.", "table"

        # Default: Latest audits
        sql = (
            "SELECT id, repo_path, total_score, grade, layer1_score, created_at "
            "FROM auditreport ORDER BY id DESC LIMIT 5"
        )
        return sql, "En son gerçekleştirilen denetim raporları listelenmiştir.", "table"

    def generate_sql(self, query: str, provider_name: str | None = None) -> tuple[str, str, str]:
        """Translates natural language query into SQL using LLM if available, otherwise rule fallback."""
        if not query or not query.strip():
            return self._fallback_rule_based_sql("")

        # Attempt LLM translation if provider is specified or default available
        try:
            from core.llm.factory import LLMProviderFactory

            p_name = provider_name or "gemini"
            llm = LLMProviderFactory.create(p_name)

            user_prompt = f"User Question: {query}\n\nGenerate the JSON output containing 'sql', 'explanation', and 'chart_type'."
            raw_response = llm.generate_response(
                prompt=user_prompt,
                system_instruction=SYSTEM_PROMPT,
            )

            if raw_response:
                # Strip markdown code blocks if wrapped
                clean_text = raw_response.strip()
                if clean_text.startswith("```"):
                    clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
                    clean_text = re.sub(r"\s*```$", "", clean_text)

                parsed = json.loads(clean_text)
                sql = parsed.get("sql")
                explanation = parsed.get("explanation", "Doğal dil sorgusu SQL'e çevrildi.")
                chart_type = parsed.get("chart_type", "table")

                if sql:
                    # Validate generated SQL
                    valid_sql = self.validate_and_sanitize_sql(sql)
                    return valid_sql, explanation, chart_type
        except Exception as e:
            logger.debug(f"LLM text-to-sql failed ({e}), falling back to heuristic engine.")

        # Fallback to deterministic rules
        sql, explanation, chart_type = self._fallback_rule_based_sql(query)
        valid_sql = self.validate_and_sanitize_sql(sql)
        return valid_sql, explanation, chart_type

    def execute_query(self, query: str, provider_name: str | None = None) -> dict[str, Any]:
        """Translates natural language to SQL, executes securely, and returns tabular results."""
        start_time = time.perf_counter()
        sql, explanation, chart_type = self.generate_sql(query, provider_name=provider_name)
        sanitized_sql = self.validate_and_sanitize_sql(sql)

        columns: list[str] = []
        rows: list[dict[str, Any]] = []

        try:
            with engine.connect() as conn:
                params: dict[str, Any] = {}
                result = conn.execute(text(sanitized_sql), params)
                columns = list(result.keys())
                for row in result.fetchall():
                    row_dict = {}
                    for col, val in zip(columns, row, strict=False):
                        # Convert non-serializable objects (like datetime) to string
                        if hasattr(val, "isoformat"):
                            row_dict[col] = val.isoformat()
                        else:
                            row_dict[col] = val
                    rows.append(row_dict)
        except Exception as e:
            logger.error(f"Failed to execute query '{sanitized_sql}': {e}")
            raise RuntimeError(f"Sorgu yürütme hatası: {e}") from e

        execution_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "query": query,
            "sql": sanitized_sql,
            "explanation": explanation,
            "chart_type": chart_type,
            "columns": columns,
            "data": rows,
            "row_count": len(rows),
            "execution_time_ms": execution_ms,
        }
