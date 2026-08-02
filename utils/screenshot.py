from __future__ import annotations

import json
import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
WHITELIST_PATH = CONFIG_DIR / "whitelist.txt"
COOKIE_WHITELIST_PATH = CONFIG_DIR / "screenshot_web_whitelist_cookie.txt"
SCREENSHOT_DIR = CONFIG_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
FIREFOX_COOKIE_DB = Path(r"C:\Users\lanlan3292\AppData\Roaming\Mozilla\Firefox\Profiles\hWXDvu56.配置文件 1\cookies.sqlite")


def load_allowed_domains() -> list[str]:
    whitelist_files = [WHITELIST_PATH, COOKIE_WHITELIST_PATH]
    domains: list[str] = []

    for path in whitelist_files:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            cleaned = line.strip().lower()
            if cleaned and not cleaned.startswith("#"):
                domains.append(cleaned)

    return sorted(set(domains))


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
    return text.replace(ip_address, "*.*.*.*")


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


def load_firefox_cookies(hostname: str, db_path: Path | None = None) -> list[dict]:
    db_file = db_path or FIREFOX_COOKIE_DB
    if not db_file.exists():
        print(f"[screenshot] Firefox cookie DB not found: {db_file}")
        return []

    temp_db_path = None
    try:
        if db_path is None:
            temp_dir = Path(tempfile.mkdtemp(prefix="firefox-cookies-", dir=str(CONFIG_DIR)))
            temp_db_path = temp_dir / "cookies.sqlite"
            shutil.copy2(db_file, temp_db_path)
            db_file = temp_db_path

        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT host, name, value, path, isSecure, expiry FROM moz_cookies WHERE ? LIKE '%' || host OR host = ?",
            (hostname, hostname),
        ).fetchall()
        conn.close()
        print(f"[screenshot] Loaded {len(rows)} cookie(s) for hostname: {hostname}")
        for row in rows:
            print(f"[screenshot] cookie -> host={row['host']} name={row['name']} path={row['path']} isSecure={row['isSecure']}")
        return [dict(row) for row in rows]
    except Exception as exc:
        print(f"[screenshot] Failed to load Firefox cookies: {exc}")
        return []
    finally:
        if temp_db_path and temp_db_path.exists():
            shutil.rmtree(temp_db_path.parent, ignore_errors=True)


async def capture_screenshot_bytes(url: str) -> bytes:
    if not is_domain_allowed(url):
        raise ValueError("Target domain is not in the whitelist")

    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""

    from playwright.async_api import async_playwright

    print(f"[screenshot] Starting Firefox for {url}")
    async with async_playwright() as playwright:
        print(f"[screenshot] Launching Firefox browser")
        browser = await playwright.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "media.volume_scale": "0.0",
                "media.default_volume": "0.0",
                "media.hardware-video-decoding.enabled": False,
                "media.autoplay.default": "5",
                "media.block-autoplay-until-in-foreground": True,
                "media.block-play-until-visible": True,
            },
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        try:
            cookies = load_firefox_cookies(hostname)
            if cookies:
                cookie_payload = []
                for cookie in cookies:
                    payload = {
                        "name": cookie["name"],
                        "value": cookie["value"],
                        "domain": cookie["host"],
                        "path": cookie["path"] or "/",
                        "secure": bool(cookie.get("isSecure", cookie.get("secure", 0))),
                        "httpOnly": False,
                        "sameSite": "Lax",
                    }
                    expiry = cookie.get("expiry")
                    if isinstance(expiry, (int, float)) and expiry > 0:
                        expiry_seconds = int(expiry / 1000 if expiry > 1_000_000_000_000 else expiry)
                        if expiry_seconds > 0:
                            payload["expires"] = expiry_seconds
                        else:
                            print(f"[screenshot] Skipping invalid expiry for cookie {cookie['name']}@{cookie['host']}: {expiry}")
                    else:
                        print(f"[screenshot] Skipping invalid expiry for cookie {cookie['name']}@{cookie['host']}: {expiry}")
                    cookie_payload.append(payload)
                print(f"[screenshot] Injecting {len(cookie_payload)} cookie(s) into context for {hostname}")
                try:
                    await context.add_cookies(cookie_payload)
                except Exception as exc:
                    print(f"[screenshot] Cookie injection failed, continuing without cookies: {exc}")
                    print(f"[screenshot] Fallback reason: Playwright rejected the injected cookie payload for {hostname}")
                    cookie_payload = []
            else:
                print(f"[screenshot] No cookies injected for {hostname}")

            page = await context.new_page()
            print(f"[screenshot] Opening page: {normalized}")
            await page.goto(normalized, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_load_state("load", timeout=60000)
            await page.wait_for_timeout(2000)
            print(f"[screenshot] Page loaded, waiting for final render")
            public_ip = get_public_ip()
            if public_ip:
                await mask_ip_in_page(page, public_ip)
            print(f"[screenshot] Capturing screenshot")
            image_bytes = await page.screenshot(full_page=False)
            print(f"[screenshot] Screenshot captured, size={len(image_bytes)} bytes")
            return image_bytes
        finally:
            await context.close()
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
