"""Test responsive design with screenshots at different breakpoints"""
import asyncio
from playwright.async_api import async_playwright
import sys

async def test_responsive():
    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # Test breakpoints: Mobile, Tablet, Desktop
        viewports = [
            {"name": "iPhone", "width": 375, "height": 667},
            {"name": "iPad", "width": 768, "height": 1024},
            {"name": "Desktop", "width": 1440, "height": 900}
        ]

        for viewport in viewports:
            print(f"\nTesting {viewport['name']} ({viewport['width']}x{viewport['height']})...")

            context = await browser.new_context(
                viewport={"width": viewport["width"], "height": viewport["height"]},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            try:
                # Navigate to dashboard
                await page.goto("http://localhost:8000/dashboard", wait_until="domcontentloaded", timeout=10000)

                # Wait for content to load
                await page.wait_for_selector('header h1', timeout=5000)

                # Take screenshot
                screenshot_path = f"C:\\Users\\Dannis Seay\\Downloads\\dashboard_{viewport['name'].lower()}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"✓ Screenshot saved: {screenshot_path}")

                # Check for responsive classes
                grid_cols = await page.locator('.grid-cols-4').count()
                print(f"  - Grid elements: {grid_cols}")

                # Check header visibility
                header_text = await page.locator('header h1').text_content()
                print(f"  - Header: {header_text}")

            except Exception as e:
                print(f"✗ Error: {e}")
            finally:
                await context.close()

        await browser.close()
        print("\n✓ Responsive design test complete!")

if __name__ == "__main__":
    asyncio.run(test_responsive())
