# etp-fair-value

Scrapers for fetching crypto ETP Portfolio Composition Files (PCF) data — daily holdings reports from BlackRock and Fidelity — and pushing fair value parameters to the TOB API.

## Supported Funds

| Script | Fund | Underlying | Provider |
|--------|------|------------|----------|
| `update_ibit.py` | IBIT (iShares Bitcoin Trust) | BTC | BlackRock |
| `update_fbtc.py` | FBTC (Fidelity Wise Origin Bitcoin Fund) | BTC | Fidelity |
| `update_feth.py` | FETH (Fidelity Ethereum Fund) | ETH | Fidelity |
| `update_etha.py` | ETHA (iShares Ethereum Trust) | ETH | BlackRock |
| `update_fsol.py` | FSOL (Fidelity Solana Fund) | SOL | Fidelity |

Each scraper downloads the fund's daily holdings report, parses it, and POSTs the numerator (crypto units held) and denominator (shares outstanding) to the API.

Standalone holdings scripts (`ibit_holdings.py`, `fbtc_holdings.py`, etc.) can be used to fetch and display holdings data without pushing to the API.

## Setup

### Requirements

```bash
pip install playwright requests pdfplumber
python -m playwright install chromium
```

### Configuration

```bash
echo "API_KEY=your_key_here" > .env
```

### Usage

```bash
python update_ibit.py
python update_fbtc.py
python update_feth.py
python update_etha.py
python update_fsol.py
```

Or fetch holdings without pushing to the API:

```bash
python ibit_holdings.py
python fbtc_holdings.py
```
