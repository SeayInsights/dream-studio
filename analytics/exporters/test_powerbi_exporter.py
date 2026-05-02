"""Tests for PowerBIExporter"""
import pytest
from pathlib import Path
from analytics.exporters.powerbi_exporter import PowerBIExporter
import json
import csv


@pytest.fixture
def sample_report_data():
    """Sample report data for testing"""
    return {
        'metadata': {
            'generated_at': '2026-05-01T12:00:00',
            'report_type': 'detailed',
            'date_range': {
                'start': '2026-04-01',
                'end': '2026-04-30',
                'days': 30
            }
        },
        'sections': [
            {
                'title': 'Skills',
                'metrics': {
                    'total_invocations': 150,
                    'success_rate_overall': 0.95,
                    'top_skills': [
                        {'name': 'dream-studio:core', 'count': 50, 'success_rate': 0.96},
                        {'name': 'dream-studio:quality', 'count': 40, 'success_rate': 0.94},
                        {'name': 'dream-studio:domains', 'count': 30, 'success_rate': 0.93}
                    ]
                }
            },
            {
                'title': 'Tokens',
                'metrics': {
                    'total_tokens': 1500000,
                    'total_cost_usd': 45.50,
                    'by_model': [
                        {'model': 'claude-sonnet-4.5', 'tokens': 1000000, 'cost': 30.00},
                        {'model': 'claude-haiku-4', 'tokens': 500000, 'cost': 15.50}
                    ]
                }
            },
            {
                'title': 'Sessions',
                'metrics': {
                    'recent_sessions': [
                        {'id': 'sess_1', 'date': '2026-04-15', 'duration': 120, 'project': 'dream-studio'},
                        {'id': 'sess_2', 'date': '2026-04-20', 'duration': 90, 'project': 'client-work'}
                    ]
                }
            },
            {
                'title': 'Models',
                'metrics': {
                    'by_model': [
                        {'model': 'claude-sonnet-4.5', 'count': 100, 'tokens': 1000000},
                        {'model': 'claude-haiku-4', 'count': 50, 'tokens': 500000}
                    ]
                }
            },
            {
                'title': 'Lessons',
                'metrics': {
                    'recent_lessons': [
                        {
                            'id': 'lesson_1',
                            'category': 'performance',
                            'description': 'Use Haiku for exploration',
                            'created_at': '2026-04-10T10:00:00'
                        }
                    ]
                }
            },
            {
                'title': 'Workflows',
                'metrics': {
                    'top_workflows': [
                        {'id': 'wf_1', 'name': 'build-test-deploy', 'count': 20, 'avg_duration': 45}
                    ]
                }
            }
        ]
    }


def test_powerbi_exporter_initialization():
    """Test PowerBIExporter initialization"""
    exporter = PowerBIExporter()
    assert exporter is not None


def test_validate_data_valid(sample_report_data):
    """Test data validation with valid data"""
    exporter = PowerBIExporter()
    error = exporter._validate_data(sample_report_data)
    assert error is None


def test_validate_data_invalid():
    """Test data validation with invalid data"""
    exporter = PowerBIExporter()

    # Not a dict
    error = exporter._validate_data("not a dict")
    assert error is not None

    # Missing sections key
    error = exporter._validate_data({'metadata': {}})
    assert error is not None

    # Sections not a list
    error = exporter._validate_data({'sections': 'not a list'})
    assert error is not None


def test_create_data_model(sample_report_data):
    """Test data model creation"""
    exporter = PowerBIExporter()
    data_model = exporter.create_data_model(sample_report_data)

    assert 'tables' in data_model
    assert 'relationships' in data_model
    assert 'measures' in data_model
    assert 'hierarchies' in data_model

    # Check tables exist
    table_names = [table['name'] for table in data_model['tables']]
    assert 'Skills' in table_names
    assert 'Tokens' in table_names
    assert 'Sessions' in table_names
    assert 'Models' in table_names
    assert 'Lessons' in table_names
    assert 'Workflows' in table_names
    assert 'Date' in table_names

    # Check measures
    assert len(data_model['measures']) > 0
    measure_names = [m['name'] for m in data_model['measures']]
    assert 'Total Tokens' in measure_names
    assert 'Total Cost USD' in measure_names


def test_build_skills_table(sample_report_data):
    """Test Skills table building"""
    exporter = PowerBIExporter()
    section_data = {section['title']: section.get('metrics', {}) for section in sample_report_data['sections']}
    skills_data = section_data['Skills']

    table = exporter._build_skills_table(skills_data)

    assert table['name'] == 'Skills'
    assert len(table['rows']) == 3  # 3 skills in sample data
    assert table['rows'][0]['skill_name'] == 'dream-studio:core'
    assert table['rows'][0]['invocations'] == 50


def test_build_tokens_table(sample_report_data):
    """Test Tokens table building"""
    exporter = PowerBIExporter()
    section_data = {section['title']: section.get('metrics', {}) for section in sample_report_data['sections']}
    tokens_data = section_data['Tokens']

    table = exporter._build_tokens_table(tokens_data)

    assert table['name'] == 'Tokens'
    assert len(table['rows']) == 2  # 2 models in sample data
    assert table['rows'][0]['model'] == 'claude-sonnet-4.5'


def test_build_date_table():
    """Test Date dimension table building"""
    exporter = PowerBIExporter()
    date_range = {
        'start': '2026-04-01',
        'end': '2026-04-05',
        'days': 5
    }

    table = exporter._build_date_table(date_range)

    assert table['name'] == 'Date'
    assert len(table['rows']) == 5  # 5 days
    assert table['rows'][0]['date'] == '2026-04-01'
    assert table['rows'][0]['year'] == 2026
    assert table['rows'][0]['month'] == 'April'


def test_generate_pbix_metadata(sample_report_data):
    """Test schema.json generation"""
    exporter = PowerBIExporter()
    data_model = exporter.create_data_model(sample_report_data)
    schema_json = exporter.generate_pbix_metadata(data_model)

    # Parse JSON
    schema = json.loads(schema_json)

    assert 'version' in schema
    assert 'tables' in schema
    assert 'relationships' in schema
    assert 'measures' in schema
    assert 'hierarchies' in schema


def test_export_dataset_success(sample_report_data, tmp_path):
    """Test full dataset export"""
    exporter = PowerBIExporter()

    output_path = tmp_path / "powerbi_export"

    success, result = exporter.export_dataset(sample_report_data, output_path)

    assert success is True
    assert Path(result).exists()

    # Check directory structure
    data_dir = Path(result) / "data"
    assert data_dir.exists()

    # Check CSV files exist
    assert (data_dir / "skills.csv").exists()
    assert (data_dir / "tokens.csv").exists()
    assert (data_dir / "sessions.csv").exists()
    assert (data_dir / "models.csv").exists()
    assert (data_dir / "lessons.csv").exists()
    assert (data_dir / "workflows.csv").exists()
    assert (data_dir / "date.csv").exists()

    # Check schema.json exists
    schema_path = Path(result) / "schema.json"
    assert schema_path.exists()

    # Check .pbids file exists
    pbids_path = Path(result) / "dataset.pbids"
    assert pbids_path.exists()

    # Check README exists
    readme_path = Path(result) / "README.txt"
    assert readme_path.exists()

    # Validate CSV structure
    with open(data_dir / "skills.csv", 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 3
        assert 'skill_id' in rows[0]
        assert 'invocations' in rows[0]

    # Validate schema.json structure
    with open(schema_path, 'r', encoding='utf-8') as f:
        schema = json.load(f)
        assert 'tables' in schema
        assert len(schema['tables']) == 7  # 6 data tables + Date table

    # Validate .pbids structure
    with open(pbids_path, 'r', encoding='utf-8') as f:
        pbids = json.load(f)
        assert 'version' in pbids
        assert 'connections' in pbids


def test_export_dataset_invalid_data(tmp_path):
    """Test export with invalid data"""
    exporter = PowerBIExporter()

    output_path = tmp_path / "powerbi_export"

    # Invalid data
    success, result = exporter.export_dataset({'invalid': 'data'}, output_path)

    assert success is False
    assert "must contain 'sections' key" in result


def test_export_csv_files(sample_report_data, tmp_path):
    """Test CSV file export"""
    exporter = PowerBIExporter()
    data_model = exporter.create_data_model(sample_report_data)

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    exported_files = exporter._export_csv_files(data_model['tables'], data_dir)

    assert len(exported_files) == 7  # 6 data tables + Date table

    # Check first file (skills.csv)
    skills_path = data_dir / "skills.csv"
    assert skills_path.exists()

    with open(skills_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) > 0


def test_generate_pbids_file(tmp_path):
    """Test .pbids file generation"""
    exporter = PowerBIExporter()

    data_dir = tmp_path / "data"
    data_dir.mkdir()

    pbids_content = exporter._generate_pbids_file(data_dir)

    # Parse JSON
    pbids = json.loads(pbids_content)

    assert pbids['version'] == '0.1'
    assert 'connections' in pbids
    assert pbids['connections'][0]['details']['protocol'] == 'file'
    assert pbids['connections'][0]['options']['fileType'] == 'csv'


def test_generate_readme(sample_report_data):
    """Test README generation"""
    exporter = PowerBIExporter()
    data_model = exporter.create_data_model(sample_report_data)

    csv_files = [
        '/path/to/skills.csv',
        '/path/to/tokens.csv'
    ]

    readme = exporter._generate_readme(csv_files, data_model)

    assert 'Dream Studio Analytics' in readme
    assert 'QUICK START' in readme
    assert 'TABLES:' in readme
    assert 'SUGGESTED MEASURES:' in readme
    assert 'RELATIONSHIPS:' in readme


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
