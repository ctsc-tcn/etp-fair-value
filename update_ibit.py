#!/usr/bin/env python3
"""
Fetches IBIT Daily Holdings from BlackRock and pushes
numerator (quantity held) and denominator (shares outstanding) to the TOB API.

Usage:
    API_KEY=yourkey venv/bin/python update_ibit.py

    Or create a .env file with:
        API_KEY=yourkey
"""

import asyncio
import os
import re
import sys
import xml.etree.ElementTree as ET

import requests
from playwright.async_api import async_playwright

# --- Config ---
MODEL_NAME = "IBIT"
PRODUCT_URL = "https://www.blackrock.com/us/individual/products/333011/"
DOWNLOAD_URL = (
    "https://www.blackrock.com/us/individual/products/333011/"
    "fund/1515394931018.ajax?fileType=xls&fileName=iShares-Bitcoin-Trust-ETF_fund&dataType=fund"
)

API_BASE = "https://bidoffermineyours.xyz/api/tob/params"


def get_api_key() -> str:
    """Load API key from environment or .env file."""
    key = os.environ.get("API_KEY")
    if key:
        return key
    from pathlib import Path
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    print("ERROR: No API_KEY found. Set API_KEY env var or create .env file.")
    sys.exit(1)


async def download_xls() -> bytes:
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

            if len(values) >= 7 and values[0] == "BTC":
                quantity_held = values[6]

        return {
            "date": date,
            "shares_outstanding": shares_outstanding,
            "quantity_held": quantity_held,
        }

    raise RuntimeError("Holdings worksheet not found in XLS")


def normalize_blackrock_date(date_str: str) -> str:
    """Convert 'Mar 24, 2026' to '2026-03-24'."""
    from datetime import datetime
    dt = datetime.strptime(date_str, "%b %d, %Y")
    return dt.strftime("%Y-%m-%d")


def post_to_api(api_key: str, numerator: float, denominator: float, holdings_date: str = None) -> dict:
    payload = {
        "model_name": MODEL_NAME,
        "numerator": numerator,
        "denominator": denominator,
    }
    if holdings_date:
        payload["holdings_date"] = holdings_date
    resp = requests.post(
        API_BASE,
        params={"api_key": api_key},
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


async def main():
    api_key = get_api_key()

    print(f"Fetching {MODEL_NAME} Daily Holdings Report...")
    xls_bytes = await download_xls()
    print(f"Downloaded XLS ({len(xls_bytes):,} bytes)")

    result = parse_xls(xls_bytes)

    print(f"\n{'=' * 50}")
    print(f"  {MODEL_NAME} Daily Holdings Report")
    print(f"{'=' * 50}")
    print(f"  Date:               {result['date']}")
    print(f"  Shares Outstanding: {result['shares_outstanding']}")
    print(f"  Quantity Held:      {result['quantity_held']}")
    print(f"{'=' * 50}")

    if "NOT FOUND" in result.values():
        print("ERROR: Could not parse all fields from XLS")
        sys.exit(1)

    numerator = float(result["quantity_held"].replace(",", ""))
    denominator = float(result["shares_outstanding"].replace(",", ""))

    holdings_date = normalize_blackrock_date(result["date"])
    print(f"\nPosting to API: {MODEL_NAME} numerator={numerator}, denominator={denominator}, date={holdings_date}")
    api_resp = post_to_api(api_key, numerator, denominator, holdings_date)
    print(f"API response: {api_resp}")

    if api_resp.get("success"):
        print(f"OK — {MODEL_NAME} params updated at {api_resp['data']['last_updated']}")
    else:
        print(f"FAILED — {api_resp}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
