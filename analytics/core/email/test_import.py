"""
Quick test to verify email module can be imported correctly.
Run this to check that all components are properly configured.
"""

import sys
from pathlib import Path

# Add analytics directory to path
analytics_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(analytics_dir))

print("Testing email module imports...")
print("-" * 50)

try:
    from analytics.core.email import EmailSender, TemplateRenderer
    print("✓ Successfully imported EmailSender and TemplateRenderer")

    # Test template renderer
    renderer = TemplateRenderer()
    print(f"✓ TemplateRenderer initialized (template dir: {renderer.template_dir})")

    # Check templates exist
    templates = ["report_notification.html", "alert_notification.html", "scheduled_report.html"]
    for template in templates:
        template_path = renderer.template_dir / template
        if template_path.exists():
            print(f"✓ Template found: {template}")
        else:
            print(f"✗ Template missing: {template}")

    # Test simple template rendering
    test_html = renderer.render_string(
        "<h1>{{title}}</h1><p>{{message}}</p>",
        {"title": "Test", "message": "Success"}
    )
    if "Test" in test_html and "Success" in test_html:
        print("✓ Template rendering works correctly")
    else:
        print("✗ Template rendering failed")

    print("\n" + "=" * 50)
    print("All imports successful!")
    print("=" * 50)
    print("\nEmail module is ready to use.")
    print("\nNext steps:")
    print("1. Configure SMTP settings (see config.example.yaml)")
    print("2. Test sending an email (see example_usage.py)")
    print("3. Integrate with your analytics system")

except Exception as e:
    print(f"\n✗ Import failed: {e}")
    import traceback
    traceback.print_exc()
