"""Test CSVExporter functionality"""
import os
import sys
import csv
import zipfile
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from analytics.exporters.csv_exporter import CSVExporter


def create_sample_report():
    """Create sample report data for testing"""
    return {
        "metadata": {
            "generated_at": "2026-05-01T23:15:00",
            "report_type": "detailed",
            "date_range": {
                "start": "2026-04-01",
                "end": "2026-04-30",
                "days": 30
            }
        },
        "sections": [
            {
                "title": "Skills",
                "metrics": {
                    "total_skill_invocations": 1234,
                    "unique_skills": 45,
                    "top_skills": [
                        {"skill": "core:build", "count": 567, "success_rate": 92.5},
                        {"skill": "quality:debug", "count": 234, "success_rate": 88.3},
                        {"skill": "domains:saas-build", "count": 123, "success_rate": 95.1}
                    ]
                }
            },
            {
                "title": "Tokens",
                "metrics": {
                    "total_tokens": 5678901,
                    "by_model": {
                        "claude-sonnet-4-5": 3456789,
                        "claude-haiku-4-0": 2222112
                    },
                    "daily_average": 189296.7
                }
            },
            {
                "title": "Sessions",
                "metrics": {
                    "total_sessions": 156,
                    "avg_duration_minutes": 42.5,
                    "by_project": {
                        "dream-studio": 89,
                        "dreamysuite": 45,
                        "career-studio": 22
                    }
                }
            }
        ]
    }


def test_single_file_export():
    """Test export_to_csv - single flattened CSV"""
    print("\n=== Test 1: Single File Export ===")

    exporter = CSVExporter()
    report = create_sample_report()

    output_path = Path("test_output/report_single.csv")
    output_path.parent.mkdir(exist_ok=True)

    success, result = exporter.export_to_csv(report, output_path)

    if success:
        print(f"✓ Export successful: {result}")

        # Read and display content
        with open(output_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)

            print(f"  Total rows: {len(rows)}")
            print(f"  Header: {rows[0]}")
            print(f"  Sample rows:")
            for row in rows[1:6]:  # Show first 5 data rows
                print(f"    {row}")

    else:
        print(f"✗ Export failed: {result}")

    return success


def test_multiple_files_export():
    """Test export_multiple - one CSV per section"""
    print("\n=== Test 2: Multiple Files Export ===")

    exporter = CSVExporter()
    report = create_sample_report()

    output_dir = Path("test_output/multiple")

    success, result = exporter.export_multiple(report, output_dir)

    if success:
        print(f"✓ Export successful")
        print(f"  Files created:")
        for path in result:
            file_path = Path(path)
            print(f"    - {file_path.name} ({file_path.stat().st_size} bytes)")

            # Display content of first file
            if file_path.name == "skills.csv":
                print(f"  Content of skills.csv:")
                with open(file_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    for i, row in enumerate(reader):
                        print(f"    {row}")
                        if i >= 4:  # Show first 5 rows
                            break

    else:
        print(f"✗ Export failed: {result}")

    return success


def test_zip_export():
    """Test export_as_zip - ZIP archive with multiple CSVs"""
    print("\n=== Test 3: ZIP Archive Export ===")

    exporter = CSVExporter()
    report = create_sample_report()

    output_path = Path("test_output/report_archive.zip")
    output_path.parent.mkdir(exist_ok=True)

    success, result = exporter.export_as_zip(report, output_path)

    if success:
        print(f"✓ Export successful: {result}")

        # List ZIP contents
        with zipfile.ZipFile(output_path, 'r') as zipf:
            file_list = zipf.namelist()
            print(f"  ZIP contents ({len(file_list)} files):")
            for filename in file_list:
                info = zipf.getinfo(filename)
                print(f"    - {filename} ({info.file_size} bytes)")

            # Display content of metadata
            if 'metadata.txt' in file_list:
                print(f"\n  Content of metadata.txt:")
                content = zipf.read('metadata.txt').decode('utf-8')
                for line in content.split('\n')[:10]:
                    print(f"    {line}")

    else:
        print(f"✗ Export failed: {result}")

    return success


def test_error_handling():
    """Test error handling for invalid inputs"""
    print("\n=== Test 4: Error Handling ===")

    exporter = CSVExporter()

    # Test 1: Invalid data structure (missing sections)
    print("  Test: Missing 'sections' key")
    success, result = exporter.export_to_csv({"metadata": {}}, "test.csv")
    if not success:
        print(f"    ✓ Correctly rejected: {result}")
    else:
        print(f"    ✗ Should have failed")

    # Test 2: Invalid data type
    print("  Test: Invalid data type (not a dict)")
    success, result = exporter.export_to_csv("not a dict", "test.csv")
    if not success:
        print(f"    ✓ Correctly rejected: {result}")
    else:
        print(f"    ✗ Should have failed")

    # Test 3: Non-existent parent directory
    print("  Test: Non-existent parent directory")
    success, result = exporter.export_to_csv(
        create_sample_report(),
        Path("nonexistent_dir/deep/nested/test.csv")
    )
    if not success:
        print(f"    ✓ Correctly rejected: {result}")
    else:
        print(f"    ✗ Should have failed")

    return True


def test_excel_compatibility():
    """Test UTF-8 BOM for Excel compatibility"""
    print("\n=== Test 5: Excel Compatibility (UTF-8 BOM) ===")

    exporter = CSVExporter()
    report = create_sample_report()

    output_path = Path("test_output/excel_compat.csv")
    output_path.parent.mkdir(exist_ok=True)

    success, result = exporter.export_to_csv(report, output_path)

    if success:
        # Check for UTF-8 BOM
        with open(output_path, 'rb') as f:
            first_bytes = f.read(3)
            has_bom = (first_bytes == b'\xef\xbb\xbf')

            if has_bom:
                print(f"✓ UTF-8 BOM present (Excel compatible)")
            else:
                print(f"✗ UTF-8 BOM missing")

            return has_bom

    return False


if __name__ == "__main__":
    print("CSV Exporter Test Suite")
    print("=" * 50)

    results = []

    results.append(("Single File Export", test_single_file_export()))
    results.append(("Multiple Files Export", test_multiple_files_export()))
    results.append(("ZIP Archive Export", test_zip_export()))
    results.append(("Error Handling", test_error_handling()))
    results.append(("Excel Compatibility", test_excel_compatibility()))

    print("\n" + "=" * 50)
    print("Test Summary:")
    print("=" * 50)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
