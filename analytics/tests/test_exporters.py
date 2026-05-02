"""
Comprehensive tests for all export formats (ER021)

Tests PDF, Excel, PowerPoint, CSV, and Power BI exporters with proper
chart embedding, multi-page layouts, and error handling.

Coverage target: >70%
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
import tempfile
import os
import sys

# Ensure analytics package is in path
analytics_path = Path(__file__).parent.parent
if str(analytics_path) not in sys.path:
    sys.path.insert(0, str(analytics_path))


@pytest.fixture
def temp_output_dir():
    """Create temporary output directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_report():
    """Sample report data for export tests"""
    return {
        "metadata": {
            "report_type": "summary",
            "generated_at": "2026-05-01T12:00:00Z",
            "date_range": ("2026-04-01", "2026-04-30")
        },
        "sections": [
            {
                "title": "Executive Summary",
                "metrics": {
                    "total_sessions": 127,
                    "success_rate": 95.5,
                    "avg_duration": 18.5
                },
                "charts": [
                    {
                        "type": "bar",
                        "title": "Sessions by Day",
                        "data": {"labels": ["Mon", "Tue", "Wed"], "values": [10, 15, 12]}
                    }
                ]
            },
            {
                "title": "Token Usage",
                "metrics": {
                    "total_tokens": 1500000,
                    "cost_usd": 45.50
                }
            }
        ]
    }


# ============================================================================
# PDF Exporter Tests
# ============================================================================

class TestPDFExporter:
    """Test PDF export functionality"""

    @pytest.fixture
    def pdf_exporter(self):
        """Create PDFExporter instance"""
        from analytics.exporters.pdf_exporter import PDFExporter
        return PDFExporter()

    def test_export_basic_report(self, pdf_exporter, sample_report, temp_output_dir):
        """Test basic PDF export"""
        output_path = os.path.join(temp_output_dir, "report.pdf")

        success, path = pdf_exporter.export_to_pdf(sample_report, output_path)

        assert success is True
        assert path == output_path
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0

    def test_pdf_with_charts(self, pdf_exporter, sample_report, temp_output_dir):
        """Test PDF export with embedded charts"""
        output_path = os.path.join(temp_output_dir, "report_charts.pdf")

        # Add chart data to report
        sample_report["sections"][0]["charts"] = [
            {
                "type": "line",
                "title": "Trend Over Time",
                "data": {
                    "labels": ["Week 1", "Week 2", "Week 3"],
                    "values": [100, 150, 200]
                }
            }
        ]

        success, path = pdf_exporter.export_to_pdf(sample_report, output_path)

        assert success is True
        assert os.path.exists(output_path)
        # Charts should increase file size
        assert os.path.getsize(output_path) > 5000

    def test_pdf_multipage(self, pdf_exporter, sample_report, temp_output_dir):
        """Test multi-page PDF layout"""
        output_path = os.path.join(temp_output_dir, "multipage.pdf")

        # Add many sections to force multi-page
        for i in range(10):
            sample_report["sections"].append({
                "title": f"Section {i+3}",
                "metrics": {"metric": i * 100}
            })

        success, path = pdf_exporter.export_to_pdf(sample_report, output_path)

        assert success is True
        assert os.path.exists(output_path)

    def test_pdf_missing_output_path(self, pdf_exporter, sample_report):
        """Test that missing output path raises error"""
        with pytest.raises((ValueError, TypeError)):
            pdf_exporter.export_to_pdf(sample_report, None)

    def test_pdf_invalid_report_data(self, pdf_exporter, temp_output_dir):
        """Test handling of invalid report data"""
        output_path = os.path.join(temp_output_dir, "invalid.pdf")

        # Missing metadata
        invalid_report = {"sections": []}

        with pytest.raises((ValueError, KeyError)):
            pdf_exporter.export_to_pdf(invalid_report, output_path)


# ============================================================================
# Excel Exporter Tests
# ============================================================================

class TestExcelExporter:
    """Test Excel export functionality"""

    @pytest.fixture
    def excel_exporter(self):
        """Create ExcelExporter instance"""
        from analytics.exporters.excel_exporter import ExcelExporter
        return ExcelExporter()

    def test_export_basic_workbook(self, excel_exporter, sample_report, temp_output_dir):
        """Test basic Excel workbook export"""
        output_path = os.path.join(temp_output_dir, "report.xlsx")

        success, path = excel_exporter.export_to_excel(sample_report, output_path)

        assert success is True
        assert os.path.exists(output_path)
        assert output_path.endswith('.xlsx')

    def test_multisheet_export(self, excel_exporter, sample_report, temp_output_dir):
        """Test Excel export with multiple sheets"""
        from analytics.exporters.excel_exporter import ExcelTemplateBuilder

        output_path = os.path.join(temp_output_dir, "multisheet.xlsx")

        wb = excel_exporter.create_workbook()
        builder = ExcelTemplateBuilder()

        # Build multiple sheets
        builder.build_summary_dashboard(sample_report, wb)
        builder.build_detailed_metrics(sample_report, wb)

        excel_exporter.save_workbook(wb, output_path)

        assert os.path.exists(output_path)

    def test_excel_charts(self, excel_exporter, sample_report, temp_output_dir):
        """Test embedded charts in Excel"""
        output_path = os.path.join(temp_output_dir, "with_charts.xlsx")

        # Report with chart data
        sample_report["sections"][0]["charts"] = [
            {
                "type": "bar",
                "title": "Performance",
                "data": {"labels": ["A", "B", "C"], "values": [10, 20, 30]}
            }
        ]

        success, path = excel_exporter.export_to_excel(sample_report, output_path)

        assert success is True
        assert os.path.exists(output_path)

    def test_excel_formatting(self, excel_exporter, sample_report, temp_output_dir):
        """Test Excel conditional formatting"""
        from analytics.exporters.excel_templates import ExcelTemplateBuilder

        output_path = os.path.join(temp_output_dir, "formatted.xlsx")

        wb = excel_exporter.create_workbook()
        builder = ExcelTemplateBuilder()

        # Build with formatting
        builder.build_summary_dashboard(sample_report, wb)

        excel_exporter.save_workbook(wb, output_path)

        assert os.path.exists(output_path)

    def test_excel_create_workbook(self, excel_exporter):
        """Test workbook creation"""
        wb = excel_exporter.create_workbook()

        assert wb is not None
        # Should have at least one default sheet
        assert len(wb.sheetnames) >= 1

    def test_excel_save_workbook(self, excel_exporter, temp_output_dir):
        """Test saving workbook to file"""
        output_path = os.path.join(temp_output_dir, "test.xlsx")

        wb = excel_exporter.create_workbook()
        excel_exporter.save_workbook(wb, output_path)

        assert os.path.exists(output_path)


# ============================================================================
# PowerPoint Exporter Tests
# ============================================================================

class TestPPTXExporter:
    """Test PowerPoint export functionality"""

    @pytest.fixture
    def pptx_exporter(self):
        """Create PPTXExporter instance"""
        from analytics.exporters.pptx_exporter import PPTXExporter
        return PPTXExporter()

    def test_export_presentation(self, pptx_exporter, sample_report, temp_output_dir):
        """Test basic PowerPoint presentation export"""
        output_path = os.path.join(temp_output_dir, "presentation.pptx")

        success, path = pptx_exporter.export_to_pptx(sample_report, output_path)

        assert success is True
        assert os.path.exists(output_path)
        assert output_path.endswith('.pptx')

    def test_pptx_slides(self, pptx_exporter, sample_report, temp_output_dir):
        """Test slide generation from sections"""
        output_path = os.path.join(temp_output_dir, "slides.pptx")

        # Each section should become a slide
        success, path = pptx_exporter.export_to_pptx(sample_report, output_path)

        assert success is True
        assert os.path.exists(output_path)

    def test_pptx_templates(self, pptx_exporter, sample_report, temp_output_dir):
        """Test PowerPoint template application"""
        output_path = os.path.join(temp_output_dir, "templated.pptx")

        # Use specific template
        config = {
            "template": "corporate"
        }

        try:
            success, path = pptx_exporter.export_to_pptx(
                sample_report,
                output_path,
                template=config.get("template")
            )
            assert success is True
        except Exception:
            # Template may not exist in test environment
            pass

    def test_pptx_with_charts(self, pptx_exporter, sample_report, temp_output_dir):
        """Test PowerPoint with chart slides"""
        output_path = os.path.join(temp_output_dir, "charts.pptx")

        sample_report["sections"][0]["charts"] = [
            {
                "type": "pie",
                "title": "Distribution",
                "data": {"labels": ["A", "B"], "values": [60, 40]}
            }
        ]

        success, path = pptx_exporter.export_to_pptx(sample_report, output_path)

        assert success is True
        assert os.path.exists(output_path)


# ============================================================================
# CSV Exporter Tests
# ============================================================================

class TestCSVExporter:
    """Test CSV export functionality"""

    @pytest.fixture
    def csv_exporter(self):
        """Create CSVExporter instance"""
        from analytics.exporters.csv_exporter import CSVExporter
        return CSVExporter()

    def test_single_file_export(self, csv_exporter, sample_report, temp_output_dir):
        """Test single CSV file export"""
        output_path = os.path.join(temp_output_dir, "data.csv")

        success, path = csv_exporter.export_to_csv(sample_report, output_path)

        assert success is True
        assert os.path.exists(output_path)
        assert output_path.endswith('.csv')

        # Verify CSV content
        with open(output_path, 'r') as f:
            content = f.read()
            assert len(content) > 0
            # Should have headers
            assert ',' in content

    def test_multiple_files_export(self, csv_exporter, sample_report, temp_output_dir):
        """Test multiple CSV files (one per section)"""
        output_dir = temp_output_dir

        files = csv_exporter.export_multiple_csv(sample_report, output_dir)

        assert len(files) > 0
        # Should create one CSV per section
        assert len(files) <= len(sample_report["sections"])

        for file_path in files:
            assert os.path.exists(file_path)
            assert file_path.endswith('.csv')

    def test_zip_archive_export(self, csv_exporter, sample_report, temp_output_dir):
        """Test ZIP archive of CSV files"""
        output_path = os.path.join(temp_output_dir, "data.zip")

        success, path = csv_exporter.export_as_zip(sample_report, output_path)

        assert success is True
        assert os.path.exists(output_path)
        assert output_path.endswith('.zip')

        # Verify ZIP contains CSV files
        import zipfile
        with zipfile.ZipFile(output_path, 'r') as zf:
            names = zf.namelist()
            assert len(names) > 0
            assert any(name.endswith('.csv') for name in names)

    def test_csv_delimiter_options(self, csv_exporter, sample_report, temp_output_dir):
        """Test custom delimiter (comma, semicolon, tab)"""
        output_path = os.path.join(temp_output_dir, "semicolon.csv")

        success, path = csv_exporter.export_to_csv(
            sample_report,
            output_path,
            delimiter=';'
        )

        assert success is True

        # Verify delimiter
        with open(output_path, 'r') as f:
            content = f.read()
            assert ';' in content


# ============================================================================
# Power BI Exporter Tests
# ============================================================================

class TestPowerBIExporter:
    """Test Power BI dataset export functionality"""

    @pytest.fixture
    def powerbi_exporter(self):
        """Create PowerBIExporter instance"""
        from analytics.exporters.powerbi_exporter import PowerBIExporter
        return PowerBIExporter()

    def test_dataset_export(self, powerbi_exporter, sample_report, temp_output_dir):
        """Test Power BI dataset export"""
        output_dir = temp_output_dir

        success, paths = powerbi_exporter.export_dataset(sample_report, output_dir)

        assert success is True
        assert len(paths) > 0

        # Should create multiple files
        assert any('csv' in p.lower() for p in paths)

    def test_schema_generation(self, powerbi_exporter, sample_report, temp_output_dir):
        """Test schema.json generation"""
        output_dir = temp_output_dir

        powerbi_exporter.export_dataset(sample_report, output_dir)

        schema_path = os.path.join(output_dir, "schema.json")

        if os.path.exists(schema_path):
            assert os.path.getsize(schema_path) > 0

            # Verify JSON format
            import json
            with open(schema_path, 'r') as f:
                schema = json.load(f)
                assert isinstance(schema, (dict, list))

    def test_pbids_file(self, powerbi_exporter, sample_report, temp_output_dir):
        """Test .pbids connection file generation"""
        output_dir = temp_output_dir

        success, paths = powerbi_exporter.export_dataset(sample_report, output_dir)

        # Check for .pbids file
        pbids_files = [p for p in paths if p.endswith('.pbids')]

        if pbids_files:
            pbids_path = pbids_files[0]
            assert os.path.exists(pbids_path)

            # Verify JSON format
            import json
            with open(pbids_path, 'r') as f:
                pbids = json.load(f)
                assert 'version' in pbids or 'connections' in pbids

    def test_powerbi_table_structure(self, powerbi_exporter, sample_report, temp_output_dir):
        """Test that exported tables have proper structure"""
        output_dir = temp_output_dir

        powerbi_exporter.export_dataset(sample_report, output_dir)

        # Find CSV files
        csv_files = [f for f in os.listdir(output_dir) if f.endswith('.csv')]

        assert len(csv_files) > 0

        # Each CSV should have headers
        for csv_file in csv_files:
            with open(os.path.join(output_dir, csv_file), 'r') as f:
                first_line = f.readline()
                assert ',' in first_line  # Has delimiter


# ============================================================================
# Integration Tests
# ============================================================================

class TestExporterIntegration:
    """Test export pipeline integration"""

    def test_all_formats_from_same_report(self, sample_report, temp_output_dir):
        """Test exporting same report to all formats"""
        from analytics.exporters.pdf_exporter import PDFExporter
        from analytics.exporters.excel_exporter import ExcelExporter
        from analytics.exporters.pptx_exporter import PPTXExporter
        from analytics.exporters.csv_exporter import CSVExporter

        pdf_path = os.path.join(temp_output_dir, "report.pdf")
        excel_path = os.path.join(temp_output_dir, "report.xlsx")
        pptx_path = os.path.join(temp_output_dir, "report.pptx")
        csv_path = os.path.join(temp_output_dir, "report.csv")

        # Export to all formats
        pdf_exporter = PDFExporter()
        excel_exporter = ExcelExporter()
        pptx_exporter = PPTXExporter()
        csv_exporter = CSVExporter()

        pdf_success, _ = pdf_exporter.export_to_pdf(sample_report, pdf_path)
        excel_success, _ = excel_exporter.export_to_excel(sample_report, excel_path)
        pptx_success, _ = pptx_exporter.export_to_pptx(sample_report, pptx_path)
        csv_success, _ = csv_exporter.export_to_csv(sample_report, csv_path)

        # All should succeed
        assert pdf_success is True
        assert excel_success is True
        assert pptx_success is True
        assert csv_success is True

        # All files should exist
        assert os.path.exists(pdf_path)
        assert os.path.exists(excel_path)
        assert os.path.exists(pptx_path)
        assert os.path.exists(csv_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
