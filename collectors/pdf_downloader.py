from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )
}
TIMEOUT = (5, 30)


def _safe_source_name(source_name: str) -> str:
    return (
        source_name.replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
        .strip("_")
        or "source"
    )


def download_pdf(url: str, source_name: str) -> str:
    today = date.today().strftime("%Y%m%d")
    destination_dir = Path("data") / today / _safe_source_name(source_name)
    destination_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(urlparse(url).path).name or "report.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"

    destination = destination_dir / filename
    if destination.exists():
        return str(destination)

    response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    destination.write_bytes(response.content)
    return str(destination)
