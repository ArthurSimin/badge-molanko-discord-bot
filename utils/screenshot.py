from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
WHITELIST_PATH = CONFIG_DIR / "whitelist.txt"
SCREENSHOT_DIR = CONFIG_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def load_allowed_domains() -> list[str]:
    if not WHITELIST_PATH.exists():
        return []

    domains: list[str] = []
    for line in WHITELIST_PATH.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip().lower()
        if cleaned and not cleaned.startswith("#"):
            domains.append(cleaned)
    return domains


def normalize_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("URL cannot be empty")

    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    if not parsed.scheme:
        parsed = parsed._replace(scheme="https")

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are supported")

    if not parsed.netloc:
        raise ValueError("URL must include a hostname")

    return parsed.geturl()


def is_domain_allowed(url: str) -> bool:
    normalized = normalize_url(url)
    hostname = urlparse(normalized).hostname or ""
    if not hostname:
        return False

    allowed_domains = load_allowed_domains()
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in allowed_domains
    )


def get_public_ip() -> str:
    request = Request("https://api.ip.sb/ip", headers={"User-Agent": "curl/8.0"})
    with urlopen(request, timeout=10) as response:
        return response.read().decode("utf-8").strip()


def mask_ip_in_text(text: str, ip_address: str) -> str:
    if not ip_address or ip_address not in text:
        return text
    return text.replace(ip_address, "**.**.**.**")


async def mask_ip_in_page(page, ip_address: str) -> None:
    if not ip_address:
        return

    await page.evaluate(
        """
        async (ip) => {
            const maskText = (text) => text.split(ip).join('**.**.**.**');
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                if (node.nodeValue) {
                    node.nodeValue = maskText(node.nodeValue);
                }
            }
        }
        """,
        ip_address,
    )


async def capture_screenshot_bytes(url: str) -> bytes:
    if not is_domain_allowed(url):
        raise ValueError("Target domain is not in the whitelist")

    normalized = normalize_url(url)

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.firefox.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        try:
            await page.goto(normalized, wait_until="domcontentloaded", timeout=60000)
            public_ip = get_public_ip()
            if public_ip:
                await mask_ip_in_page(page, public_ip)
            return await page.screenshot(full_page=False)
        finally:
            await browser.close()


async def capture_screenshot(url: str, output_path: Path | None = None) -> Path:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    host = parsed.hostname or "page"
    slug = re.sub(r"[^a-z0-9]+", "-", host.lower()).strip("-") or "page"
    if output_path is None:
        file_name = f"{slug}-{int(time.time())}.png"
        output_path = SCREENSHOT_DIR / file_name

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_bytes = await capture_screenshot_bytes(normalized)
    output_path.write_bytes(image_bytes)
    return output_path
