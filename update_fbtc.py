#!/usr/bin/env python3
"""
Fetches FBTC Daily Holdings from Fidelity and pushes
numerator (quantity held) and denominator (shares outstanding) to the TOB API.

Usage:
    API_KEY=yourkey venv/bin/python update_fbtc.py

    Or create a .env file with:
        API_KEY=yourkey
"""

import asyncio
import re
import sys
import os
import tempfile
from pathlib import Path

import pdfplumber
import requests
from playwright.async_api import async_playwright

from notify import send_success, send_failure

# --- Config ---
TICKER = "FBTC"
MODEL_NAME = "FBTC"

API_BASE = "https://bidoffermineyours.xyz/api/tob/params"

SESSION_URL = (
    "https://digital.fidelity.com/prgw/digital/research/quote/dashboard/summary"
    f"?symbol={TICKER}"
)


def get_api_key() -> str:
    """Load API key from environment or .env file."""
    key = os.environ.get("API_KEY")
    if key:
        return key
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("API_KEY=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    print("ERROR: No API_KEY found. Set API_KEY env var or create .env file.")
    sys.exit(1)


async def download_pdf() -> bytes:
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
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # 1) Visit the FBTC summary page
        print("  Loading summary page...")
        await page.goto(SESSION_URL, timeout=30000)
        await page.wait_for_timeout(5000)

        # 2) Click "Prospectus & reports" (opens new tab)
        print("  Clicking 'Prospectus & reports'...")
        link = page.locator("a:has-text('Prospectus & reports')")
        async with context.expect_page() as new_page_info:
            await link.click()
        prosp_page = await new_page_info.value
        await prosp_page.wait_for_load_state("networkidle", timeout=30000)

        # 3) Click "Daily Holdings Report" tab
        print("  Clicking 'Daily Holdings Report' tab...")
        daily_tab = prosp_page.locator("a:has-text('Daily Holdings Report')")
        await daily_tab.click()
        await prosp_page.wait_for_timeout(3000)

        # 4) Extract the PDF URL from the iframe src
        iframe = prosp_page.locator("iframe").first
        iframe_src = await iframe.get_attribute("src")
        pdf_url = (
            "https://www.actionsxchangerepository.fidelity.com/ShowDocument/"
            + iframe_src.replace("pdfReaderStatus=Y", "pdfReaderStatus=N")
        )
        print(f"  PDF URL: {pdf_url[:100]}...")

        # 5) Fetch the PDF via in-page fetch() to carry proper cookies
        import base64
        pdf_b64 = await prosp_page.evaluate("""async (url) => {
            const resp = await fetch(url);
            const buf = await resp.arrayBuffer();
            const bytes = new Uint8Array(buf);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
            return btoa(binary);
        }""", pdf_url)
        body = base64.b64decode(pdf_b64)
        await browser.close()

        if not body.startswith(b"%PDF"):
            raise RuntimeError("Downloaded content is not a PDF")
        return body


def parse_pdf(pdf_bytes: bytes) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        tmp_path = f.name

    try:
        with pdfplumber.open(tmp_path) as pdf:
            text = "\n".join(pg.extract_text() or "" for pg in pdf.pages)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    date_match = re.search(r"Holding as of:\s*(\S+)", text)
    date = date_match.group(1) if date_match else "NOT FOUND"

    shares_match = re.search(r"Current Shares Outstanding:\s*([\d,]+)", text)
    shares_outstanding = shares_match.group(1) if shares_match else "NOT FOUND"

    qty_match = re.search(r"Crypto Asset\s+US Dollar\s+([\d,.]+)", text)
    quantity_held = qty_match.group(1) if qty_match else "NOT FOUND"

    return {
        "date": date,
        "shares_outstanding": shares_outstanding,
        "quantity_held": quantity_held,
    }


def normalize_fidelity_date(date_str: str) -> str:
    """Convert '23-MAR-26' to '2026-03-23'."""
    from datetime import datetime
    dt = datetime.strptime(date_str, "%d-%b-%y")
    return dt.strftime("%Y-%m-%d")


def post_to_api(api_key: str, numerator: float, denominator: float, holdings_date: str = None) -> dict:
    """POST numerator/denominator to the TOB API."""
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
    try:
        api_key = get_api_key()

        print(f"Fetching {TICKER} Daily Holdings Report...")
        pdf_bytes = await download_pdf()
        print(f"Downloaded PDF ({len(pdf_bytes):,} bytes)")

        result = parse_pdf(pdf_bytes)

        print(f"\n{'=' * 50}")
        print(f"  {TICKER} Daily Holdings Report")
        print(f"{'=' * 50}")
        print(f"  Date:               {result['date']}")
        print(f"  Shares Outstanding: {result['shares_outstanding']}")
        print(f"  Quantity Held:      {result['quantity_held']}")
        print(f"{'=' * 50}")

        if "NOT FOUND" in result.values():
            raise RuntimeError("Could not parse all fields from PDF")

        numerator = float(result["quantity_held"].replace(",", ""))
        denominator = float(result["shares_outstanding"].replace(",", ""))

        holdings_date = normalize_fidelity_date(result["date"])
        print(f"\nPosting to API: {MODEL_NAME} numerator={numerator}, denominator={denominator}, date={holdings_date}")
        api_resp = post_to_api(api_key, numerator, denominator, holdings_date)
        print(f"API response: {api_resp}")

        if api_resp.get("success"):
            print(f"OK — {MODEL_NAME} params updated at {api_resp['data']['last_updated']}")
            send_success(MODEL_NAME, holdings_date, numerator, denominator, api_resp['data']['last_updated'])
        else:
            raise RuntimeError(f"API rejected: {api_resp}")

    except Exception as e:
        print(f"ERROR: {e}")
        send_failure(MODEL_NAME, e)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
