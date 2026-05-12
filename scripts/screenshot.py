"""Capture a screenshot of the Streamlit dashboard for the README.

Usage: screenshot.py <url> <output_path>
"""
import sys
from playwright.sync_api import sync_playwright


def main(url: str, out_path: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1440, "height": 1100},
                                  device_scale_factor=2)
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=60_000)
        # Wait for the Plotly charts and dataframes to settle.
        page.wait_for_selector("text=Spending over Time", timeout=30_000)
        page.wait_for_selector(".js-plotly-plot", timeout=30_000)
        page.wait_for_selector("text=Year-over-Year Comparison", timeout=30_000)
        page.wait_for_timeout(3_000)
        page.screenshot(path=out_path, full_page=True)
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
