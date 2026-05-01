#!/usr/bin/env python3
"""
Fetches the FSOL Daily Holdings Report from Fidelity and extracts:
- Date
- Shares Outstanding
- Solana Quantity Held

Usage:
    venv/bin/python fsol_holdings.py

Requirements:
    pip install playwright pdfplumber
    python -m playwright install chromium
"""

import asyncio
import re
import sys
import tempfile
from pathlib import Path

import pdfplumber
from playwright.async_api import async_playwright

TICKER = "FSOL"

SESSION_URL = (
    "https://digital.fidelity.com/prgw/digital/research/quote/dashboard/summary"
    f"?symbol={TICKER}"
)


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

        # 1) Visit the summary page
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


async def main():
    print(f"Fetching {TICKER} Daily Holdings Report...")
    pdf_bytes = await download_pdf()
    print(f"Downloaded PDF ({len(pdf_bytes):,} bytes)")

    result = parse_pdf(pdf_bytes)

    print(f"\n{'=' * 45}")
    print(f"  {TICKER} Daily Holdings Report")
    print(f"{'=' * 45}")
    print(f"  Date:               {result['date']}")
    print(f"  Shares Outstanding: {result['shares_outstanding']}")
    print(f"  Quantity Held:      {result['quantity_held']}")
    print(f"{'=' * 45}")

    return result


if __name__ == "__main__":
    result = asyncio.run(main())
    if "NOT FOUND" in result.values():
        sys.exit(1)
