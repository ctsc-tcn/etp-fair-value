#!/usr/bin/env python3
"""Discord webhook notifications for update scripts."""

import os
import traceback
from pathlib import Path

import requests


def _get_webhook_url() -> str | None:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if url:
        return url
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DISCORD_WEBHOOK_URL=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip()
    return None


def send_success(model: str, date: str, numerator: float, denominator: float, last_updated: str):
    url = _get_webhook_url()
    if not url:
        return
    ratio = numerator / denominator if denominator else 0
    msg = (
        f"**{model}** updated\n"
        f"```\n"
        f"Date:               {date}\n"
        f"Quantity Held:      {numerator:,.2f}\n"
        f"Shares Outstanding: {denominator:,.2f}\n"
        f"Ratio:              {ratio:.10f}\n"
        f"Last Updated:       {last_updated}\n"
        f"```"
    )
    try:
        requests.post(url, json={"content": msg}, timeout=5)
    except Exception:
        pass


def send_failure(model: str, error: Exception):
    url = _get_webhook_url()
    if not url:
        return
    tb = traceback.format_exception(error)
    tb_str = "".join(tb)[-1500:]  # trim to fit Discord limit
    msg = (
        f"**{model}** FAILED\n"
        f"```\n{tb_str}\n```"
    )
    try:
        requests.post(url, json={"content": msg}, timeout=5)
    except Exception:
        pass
