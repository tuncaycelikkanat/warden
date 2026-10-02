"""Unit tests for NaturalLanguageQueryService (Text-to-SQL & Security Guardrails)."""

import pytest

from core.services.nl_query_service import NaturalLanguageQueryService


@pytest.fixture
def service() -> NaturalLanguageQueryService:
    return NaturalLanguageQueryService()


class TestNaturalLanguageQueryService:
    def test_fallback_lowest_scores(self, service: NaturalLanguageQueryService) -> None:
        sql, explanation, chart = service.generate_sql("En düşük kaliteli 5 proje")
        assert "order by total_score asc" in sql.lower()
        assert "limit 5" in sql.lower()
        assert chart == "bar_chart"
        assert "düşük" in explanation.lower()

    def test_fallback_highest_scores(self, service: NaturalLanguageQueryService) -> None:
        sql, explanation, chart = service.generate_sql("En başarılı ve en yüksek skorlu projeler")
        assert "order by total_score desc" in sql.lower()
        assert chart == "bar_chart"

    def test_fallback_grade_distribution(self, service: NaturalLanguageQueryService) -> None:
        sql, explanation, chart = service.generate_sql("Sistemdeki not dağılımı nasıl?")
        assert "group by grade" in sql.lower()
        assert chart == "bar_chart"

    def test_fallback_security_focus(self, service: NaturalLanguageQueryService) -> None:
        sql, explanation, chart = service.generate_sql("Güvenlik puanı en zayıf olanlar")
        assert "group_security" in sql.lower()
        assert chart == "bar_chart"

    def test_fallback_average_stats(self, service: NaturalLanguageQueryService) -> None:
        sql, explanation, chart = service.generate_sql("Tüm denetimlerin ortalama puanı ve genel özet")
        assert "avg(total_score)" in sql.lower()
        assert chart == "stat_card"

    def test_fallback_trend_timeline(self, service: NaturalLanguageQueryService) -> None:
        sql, explanation, chart = service.generate_sql("Skorların zaman içindeki trend grafiği")
        assert "audit_date" in sql.lower()
        assert chart == "line_chart"

    def test_guardrail_rejects_drop_table(self, service: NaturalLanguageQueryService) -> None:
        with pytest.raises(ValueError, match="Güvenlik İhlali"):
            service.validate_and_sanitize_sql("DROP TABLE auditreport")

    def test_guardrail_rejects_delete_and_update(self, service: NaturalLanguageQueryService) -> None:
        with pytest.raises(ValueError, match="Güvenlik İhlali"):
            service.validate_and_sanitize_sql("DELETE FROM auditreport WHERE id = 1")

        with pytest.raises(ValueError, match="Güvenlik İhlali"):
            service.validate_and_sanitize_sql("UPDATE auditreport SET total_score = 100")

    def test_guardrail_rejects_stacked_queries(self, service: NaturalLanguageQueryService) -> None:
        with pytest.raises(ValueError, match="Çoklu SQL ifadesi"):
            service.validate_and_sanitize_sql("SELECT * FROM auditreport; DROP TABLE auditreport")

    def test_guardrail_rejects_unwhitelisted_table(self, service: NaturalLanguageQueryService) -> None:
        with pytest.raises(ValueError, match="Yalnızca WARDEN audit tabloları"):
            service.validate_and_sanitize_sql("SELECT * FROM sqlite_master")

    def test_guardrail_enforces_limit_100(self, service: NaturalLanguageQueryService) -> None:
        # Appends LIMIT 100 if missing
        sql_no_limit = service.validate_and_sanitize_sql("SELECT id, repo_path FROM auditreport")
        assert "limit 100" in sql_no_limit.lower()

        # Clamps excessive limit
        sql_high_limit = service.validate_and_sanitize_sql("SELECT id, repo_path FROM auditreport LIMIT 500")
        assert "limit 100" in sql_high_limit.lower()
        assert "500" not in sql_high_limit

    def test_execute_query_runs_and_returns_data(self, service: NaturalLanguageQueryService) -> None:
        result = service.execute_query("En son 3 denetim raporu")
        assert isinstance(result, dict)
        assert result["query"] == "En son 3 denetim raporu"
        assert "SELECT" in result["sql"]
        assert "columns" in result
        assert "data" in result
        assert "chart_type" in result
        assert isinstance(result["execution_time_ms"], float)
