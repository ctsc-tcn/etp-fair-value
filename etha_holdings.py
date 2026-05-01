#!/usr/bin/env python3
"""
Fetches ETHA (iShares Ethereum Trust ETF) Daily Holdings from BlackRock
and extracts:
- Date
- Shares Outstanding
- ETH Units (Quantity Held)

Usage:
    venv/bin/python etha_holdings.py

Requirements:
    pip install playwright
    python -m playwright install chromium
"""

import asyncio
import re
import sys
import xml.etree.ElementTree as ET

from playwright.async_api import async_playwright

PRODUCT_URL = "https://www.blackrock.com/us/individual/products/337614/"

DOWNLOAD_URL = (
    "https://www.blackrock.com/us/individual/products/337614/"
    "fund/1515394931018.ajax?fileType=xls&fileName=iShares-Ethereum-Trust-ETF_fund&dataType=fund"
)


async def download_xls() -> bytes:
    """Navigate to BlackRock, establish session, download the XLS file."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        await page.goto(PRODUCT_URL, timeout=30000)
        await page.wait_for_timeout(3000)

        try:
            await page.locator("#onetrust-accept-btn-handler").click(timeout=3000)
            await page.wait_for_timeout(1000)
        except Exception:
            pass

        resp = await context.request.get(DOWNLOAD_URL)
        body = await resp.body()
        await browser.close()

        if not body or b"Workbook" not in body[:500]:
            raise RuntimeError("Downloaded content is not an XLS workbook")
        return body


def parse_xls(xls_bytes: bytes) -> dict:
    """Parse the XML Spreadsheet and extract holdings data."""
    content = xls_bytes.decode("utf-8-sig")
    content = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", content)

    root = ET.fromstring(content)
    ns = {"ss": "urn:schemas-microsoft-com:office:spreadsheet"}

    for ws in root.findall(".//ss:Worksheet", ns):
        name = ws.get("{urn:schemas-microsoft-com:office:spreadsheet}Name")
        if name != "Holdings":
            continue

        table = ws.find("ss:Table", ns)
        rows = table.findall("ss:Row", ns)

        date = "NOT FOUND"
        shares_outstanding = "NOT FOUND"
        quantity_held = "NOT FOUND"

        for row in rows:
            cells = row.findall("ss:Cell", ns)
            values = []
            for cell in cells:
                data = cell.find("ss:Data", ns)
                values.append(data.text if data is not None else "")

            if len(values) >= 2:
                if values[0] == "Fund Holdings as of":
                    date = values[1]
                if values[0] == "Shares Outstanding":
                    shares_outstanding = values[1]

            # Holdings row: Ticker=ETH, Name=ETHER, ..., Units/Shares at index 6
            if len(values) >= 7 and values[0] == "ETH":
                quantity_held = values[6]

        return {
            "date": date,
            "shares_outstanding": shares_outstanding,
            "quantity_held": quantity_held,
        }

    raise RuntimeError("Holdings worksheet not found in XLS")


async def main():
    print("Fetching ETHA Daily Holdings Report...")
    xls_bytes = await download_xls()
    print(f"Downloaded XLS ({len(xls_bytes):,} bytes)")

    result = parse_xls(xls_bytes)

    print(f"\n{'=' * 50}")
    print("  ETHA Daily Holdings Report")
    print(f"{'=' * 50}")
    print(f"  Date:               {result['date']}")
    print(f"  Shares Outstanding: {result['shares_outstanding']}")
    print(f"  Quantity Held:      {result['quantity_held']}")
    print(f"{'=' * 50}")

    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    if "NOT FOUND" in result.values():
        sys.exit(1)
