"""
Comprehensive tests for analytics report generation (ER020)

Tests ReportGenerator's ability to create summary, detailed, executive,
and custom reports with proper metric compilation and template rendering.

Coverage target: >70%
"""
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import os
import tempfile

# Import after ensuring analytics package is in path
import sys
analytics_path = Path(__file__).parent.parent
if str(analytics_path) not in sys.path:
    sys.path.insert(0, str(analytics_path))

from analytics.core.reports.generator import ReportGenerator


@pytest.fixture
def temp_db():
    """Create temporary test database"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name

    yield db_path

    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.fixture
def mock_collectors():
    """Mock all collector classes"""
    with patch('analytics.core.reports.generator.SkillCollector') as skill, \
         patch('analytics.core.reports.generator.TokenCollector') as token, \
         patch('analytics.core.reports.generator.SessionCollector') as session, \
         patch('analytics.core.reports.generator.ModelCollector') as model, \
         patch('analytics.core.reports.generator.LessonCollector') as lesson, \
         patch('analytics.core.reports.generator.WorkflowCollector') as workflow:

        # Configure mock return values
        skill.return_value.collect.return_value = {
            'total_skills': 45,
            'success_rate': 95.5,
            'avg_duration': 12.3
        }

        token.return_value.collect.return_value = {
            'total_tokens': 1500000,
            'input_tokens': 900000,
            'output_tokens': 600000,
            'avg_per_session': 15000
        }

        session.return_value.collect.return_value = {
            'total_sessions': 127,
            'avg_duration': 18.5,
            'active_users': 5
        }

        model.return_value.collect.return_value = {
            'total_requests': 450,
            'by_model': {
                'claude-sonnet-4.5': 300,
                'claude-haiku-4': 150
            }
        }

        lesson.return_value.collect.return_value = {
            'total_lessons': 23,
            'categories': {'bug_fix': 8, 'optimization': 15}
        }

        workflow.return_value.collect.return_value = {
            'total_workflows': 67,
            'success_rate': 92.0
        }

        yield {
            'skill': skill,
            'token': token,
            'session': session,
            'model': model,
            'lesson': lesson,
            'workflow': workflow
        }


class TestReportGenerator:
    """Test ReportGenerator functionality"""

    def test_init_default_db_path(self, mock_collectors):
        """Test initialization with default database path"""
        generator = ReportGenerator()

        expected_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        assert generator.db_path == expected_path
        assert generator.skill_collector is not None
        assert generator.token_collector is not None

    def test_init_custom_db_path(self, temp_db, mock_collectors):
        """Test initialization with custom database path"""
        generator = ReportGenerator(db_path=temp_db)

        assert generator.db_path == temp_db

    def test_init_expands_tilde(self, mock_collectors):
        """Test that ~ is expanded in db_path"""
        generator = ReportGenerator(db_path="~/custom/path.db")

        assert "~" not in generator.db_path
        assert generator.db_path == os.path.expanduser("~/custom/path.db")

    def test_generate_summary_report(self, mock_collectors):
        """Test summary report generation"""
        generator = ReportGenerator()
        report = generator.generate_report("summary")

        # Check metadata
        assert report["metadata"]["report_type"] == "summary"
        assert "generated_at" in report["metadata"]
        assert "date_range" in report["metadata"]

        # Check sections exist
        assert "sections" in report
        assert isinstance(report["sections"], list)
        assert len(report["sections"]) > 0

        # Summary should have 3-5 sections
        assert 3 <= len(report["sections"]) <= 5

    def test_generate_detailed_report(self, mock_collectors):
        """Test detailed report generation"""
        generator = ReportGenerator()
        report = generator.generate_report("detailed")

        assert report["metadata"]["report_type"] == "detailed"
        assert "sections" in report

        # Detailed should have 8-10 sections
        assert 8 <= len(report["sections"]) <= 10

        # Should include all collector data
        section_titles = [s["title"] for s in report["sections"]]
        assert any("skill" in t.lower() for t in section_titles)
        assert any("token" in t.lower() for t in section_titles)
        assert any("session" in t.lower() for t in section_titles)

    def test_generate_executive_report(self, mock_collectors):
        """Test executive report generation (business metrics)"""
        generator = ReportGenerator()
        report = generator.generate_report("executive")

        assert report["metadata"]["report_type"] == "executive"

        # Executive reports focus on business metrics
        section_titles = [s["title"] for s in report["sections"]]
        # Should prioritize high-level KPIs
        assert len(report["sections"]) >= 3

    def test_generate_custom_report(self, mock_collectors):
        """Test custom report with user-defined template"""
        generator = ReportGenerator()

        custom_template = {
            "sections": [
                {
                    "title": "Custom Section 1",
                    "metrics": ["skills_success_rate", "sessions_avg_duration"]
                },
                {
                    "title": "Custom Section 2",
                    "metrics": ["tokens_total", "workflows_success_rate"]
                }
            ]
        }

        report = generator.generate_report(
            "custom",
            config={"template": custom_template}
        )

        assert report["metadata"]["report_type"] == "custom"
        assert len(report["sections"]) == 2
        assert report["sections"][0]["title"] == "Custom Section 1"
        assert report["sections"][1]["title"] == "Custom Section 2"

    def test_template_rendering(self, mock_collectors):
        """Test that templates are properly rendered with data"""
        generator = ReportGenerator()
        report = generator.generate_report("summary")

        # Each section should have structure
        for section in report["sections"]:
            assert "title" in section
            assert "metrics" in section or "content" in section

    def test_metric_compilation(self, mock_collectors):
        """Test metric gathering from all collectors"""
        generator = ReportGenerator()

        date_range = (
            (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            datetime.now().strftime("%Y-%m-%d")
        )

        metrics = generator.compile_metrics(date_range)

        # Should contain data from all collectors
        assert "skills" in metrics or "skill" in str(metrics).lower()
        assert "tokens" in metrics or "token" in str(metrics).lower()
        assert "sessions" in metrics or "session" in str(metrics).lower()

    def test_date_range_handling_tuple(self, mock_collectors):
        """Test date range as tuple of strings"""
        generator = ReportGenerator()

        config = {
            "date_range": ("2026-04-01", "2026-04-30")
        }

        report = generator.generate_report("summary", config=config)

        assert report["metadata"]["date_range"] == ("2026-04-01", "2026-04-30")

    def test_date_range_handling_default(self, mock_collectors):
        """Test default date range (last 30 days)"""
        generator = ReportGenerator()
        report = generator.generate_report("summary")

        # Should have date_range in metadata
        assert "date_range" in report["metadata"]
        assert isinstance(report["metadata"]["date_range"], tuple)
        assert len(report["metadata"]["date_range"]) == 2

    def test_date_range_handling_relative(self, mock_collectors):
        """Test relative date ranges (last 7 days, etc)"""
        generator = ReportGenerator()

        config = {
            "date_range": "last_7_days"
        }

        # Should handle relative ranges gracefully
        try:
            report = generator.generate_report("summary", config=config)
            # If supported, check it worked
            assert "date_range" in report["metadata"]
        except ValueError:
            # If not supported, that's also valid
            pass

    def test_invalid_report_type(self, mock_collectors):
        """Test that invalid report type raises error"""
        generator = ReportGenerator()

        with pytest.raises(ValueError, match="Invalid report_type"):
            generator.generate_report("invalid_type")

    def test_invalid_date_range_format(self, mock_collectors):
        """Test that invalid date range format raises error"""
        generator = ReportGenerator()

        config = {
            "date_range": "not-a-valid-format"
        }

        with pytest.raises(ValueError, match="date_range"):
            generator.generate_report("summary", config=config)

    def test_custom_report_missing_template(self, mock_collectors):
        """Test that custom report without template raises error"""
        generator = ReportGenerator()

        with pytest.raises(ValueError, match="template"):
            generator.generate_report("custom")

    def test_custom_report_invalid_template_format(self, mock_collectors):
        """Test that malformed template raises error"""
        generator = ReportGenerator()

        # Template is not a dict
        with pytest.raises(ValueError, match="template.*dict"):
            generator.generate_report("custom", config={"template": "not-a-dict"})

        # Template missing sections
        with pytest.raises(ValueError, match="sections"):
            generator.generate_report("custom", config={"template": {"other": "data"}})

    def test_report_metadata_structure(self, mock_collectors):
        """Test that all reports have complete metadata"""
        generator = ReportGenerator()
        report = generator.generate_report("summary")

        metadata = report["metadata"]

        # Required fields
        assert "generated_at" in metadata
        assert "report_type" in metadata
        assert "date_range" in metadata

        # generated_at should be valid ISO datetime
        datetime.fromisoformat(metadata["generated_at"].replace('Z', '+00:00'))

    def test_empty_config(self, mock_collectors):
        """Test report generation with empty config dict"""
        generator = ReportGenerator()
        report = generator.generate_report("summary", config={})

        assert report["metadata"]["report_type"] == "summary"
        assert "sections" in report

    def test_none_config(self, mock_collectors):
        """Test report generation with None config"""
        generator = ReportGenerator()
        report = generator.generate_report("summary", config=None)

        assert report["metadata"]["report_type"] == "summary"
        assert "sections" in report

    def test_sections_have_required_fields(self, mock_collectors):
        """Test that each section has required structure"""
        generator = ReportGenerator()
        report = generator.generate_report("detailed")

        for section in report["sections"]:
            # Each section must have a title
            assert "title" in section
            assert isinstance(section["title"], str)
            assert len(section["title"]) > 0


class TestReportIntegration:
    """Integration tests with real database (if available)"""

    @pytest.mark.skipif(
        not Path.home().joinpath(".dream-studio/state/studio.db").exists(),
        reason="Requires real studio.db for integration test"
    )
    def test_real_database_summary(self):
        """Test with actual database if available"""
        generator = ReportGenerator()
        report = generator.generate_report("summary")

        assert report["metadata"]["report_type"] == "summary"
        assert len(report["sections"]) > 0

    @pytest.mark.skipif(
        not Path.home().joinpath(".dream-studio/state/studio.db").exists(),
        reason="Requires real studio.db for integration test"
    )
    def test_real_database_all_types(self):
        """Test all report types with real database"""
        generator = ReportGenerator()

        for report_type in ["summary", "detailed", "executive"]:
            report = generator.generate_report(report_type)
            assert report["metadata"]["report_type"] == report_type
            assert len(report["sections"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
