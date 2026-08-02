from __future__ import annotations

import json
import os
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
BLACKLIST_PATH = CONFIG_DIR / "blacklist.txt"
COOKIE_WHITELIST_PATH = CONFIG_DIR / "screenshot_web_whitelist_cookie.txt"
SCREENSHOT_DIR = CONFIG_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
FIREFOX_COOKIE_DB = Path(os.getenv("FIREFOX_COOKIE_DB", "")) if os.getenv("FIREFOX_COOKIE_DB") else None
ALLOWED_SCHEMES = {"http", "https", "file", "ftp", "ftps", "sftp", "about"}


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


def load_blocked_domains() -> list[str]:
    if not BLACKLIST_PATH.exists():
        return []

    domains: list[str] = []
    for line in BLACKLIST_PATH.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip().lower()
        if cleaned and not cleaned.startswith("#"):
            domains.append(cleaned)

    return sorted(set(domains))


def normalize_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("URL cannot be empty")

    parsed = urlparse(cleaned)
    if not parsed.scheme:
        if "://" in cleaned:
            raise ValueError("URL must include a valid scheme")
        return f"https://{cleaned}"

    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Unsupported URL scheme: {scheme}")

    if scheme in {"http", "https", "ftp", "ftps", "sftp"} and not parsed.netloc:
        raise ValueError("URL must include a hostname")

    return parsed.geturl()


def get_navigation_wait_strategy(url: str) -> tuple[str, int]:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    scheme = (parsed.scheme or "").lower()
    if scheme in {"about", "file"}:
        return "commit", 15000
    return "domcontentloaded", 60000


async def navigate_to_page(page, url: str) -> None:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    scheme = (parsed.scheme or "").lower()

    if scheme == "about":
        try:
            await page.goto(normalized, wait_until="commit", timeout=10000)
        except Exception:
            try:
                await page.goto("about:blank", wait_until="commit", timeout=1000)
            except Exception:
                pass

            try:
                await page.evaluate(
                    """
                    (content) => {
                        document.open();
                        document.write(content);
                        document.close();
                    }
                    """,
                    "<html><body><h1>about: page</h1><pre>{}</pre></body></html>".format(normalized),
                )
            except Exception:
                await page.set_content(
                    "<html><body><h1>about: page</h1><pre>{}</pre></body></html>".format(normalized),
                )
        return

    wait_strategy, timeout_ms = get_navigation_wait_strategy(normalized)
    try:
        await page.goto(normalized, wait_until=wait_strategy, timeout=timeout_ms)
    except Exception as exc:
        print(f"[screenshot] Navigation warning for {normalized}: {exc}")
        if wait_strategy == "commit":
            await page.goto(normalized, wait_until="commit", timeout=10000)
        else:
            raise


def _pattern_matches(value: str, pattern: str) -> bool:
    candidate = pattern.strip().lower()
    if not candidate:
        return False
    if candidate == "*":
        return True

    normalized = value.strip().lower()
    regex = re.escape(candidate).replace(r"\*", ".*")
    try:
        if re.fullmatch(regex, normalized):
            return True
    except re.error:
        return False

    if normalized == candidate or normalized.endswith(f".{candidate}"):
        return True

    return False


def is_domain_allowed(url: str) -> bool:
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()

    blocked_domains = load_blocked_domains()
    for pattern in blocked_domains:
        if _pattern_matches(normalized, pattern):
            return False
        if hostname and _pattern_matches(hostname, pattern):
            return False
        if scheme and _pattern_matches(scheme, pattern):
            return False

    allowed_domains = load_allowed_domains()
    for pattern in allowed_domains:
        if _pattern_matches(normalized, pattern):
            return True
        if hostname and _pattern_matches(hostname, pattern):
            return True
        if scheme and _pattern_matches(scheme, pattern):
            return True

    return False


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


def _normalize_cookie_host(hostname: str) -> str:
    cleaned = hostname.strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
    return parsed.hostname or ""


def load_firefox_cookies(hostname: str, db_path: Path | None = None) -> list[dict]:
    db_file = db_path or FIREFOX_COOKIE_DB
    if db_file is None:
        print("[screenshot] Firefox cookie DB path is not configured")
        return []
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

        cookie_hostname = _normalize_cookie_host(hostname)
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT host, name, value, path, isSecure, expiry FROM moz_cookies WHERE ? LIKE '%' || host OR host = ?",
            (cookie_hostname, cookie_hostname),
        ).fetchall()
        conn.close()
        print(f"[screenshot] Loaded {len(rows)} cookie(s) for hostname: {hostname} (normalized: {cookie_hostname})")
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
                "media.autoplay.default": 5,
                "media.block-autoplay-until-in-foreground": True,
                "media.block-play-until-visible": True,
                "media.navigator.enabled": False,
                "media.peerconnection.ice.proxy_only_if_single_homed": True,
                "media.peerconnection.ice.default_address_only": True,
                "media.peerconnection.ice.no_host": True,
                #"general.useragent.override": "Mozilla/5.0 (compatible; MolankoBot/1.0)",
                "intl.accept_languages": "en-US,en",
                "general.useragent.locale": "en-US",
                "browser.search.region": "US",
                #"browser.cache.disk.enable": False,
                #"browser.cache.memory.enable": False
                #"pdfjs.disabled": True
                "toolkit.telemetry.enabled": False,
                "datareporting.healthreport.uploadEnabled": False,
            },
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 720},locale="en-US",timezone_id="UTC",extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
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
            await navigate_to_page(page, normalized)

            try:
                await page.wait_for_load_state("load", timeout=60000)
            except Exception as exc:
                print(f"[screenshot] Load state warning for {normalized}: {exc}")
            await page.wait_for_timeout(2000)
            print(f"[screenshot] Page loaded, waiting for final render")
            try:
                public_ip = get_public_ip()
            except Exception as exc:
                print(f"[screenshot] Failed to resolve public IP, continuing without masking: {exc}")
                public_ip = ""
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
