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
from datetime import datetime
from fnmatch import fnmatch  # 用于 glob 匹配

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
WHITELIST_PATH = CONFIG_DIR / "screenshot_web_whitelist.txt"
BLACKLIST_PATH = CONFIG_DIR / "screenshot_web_blacklist.txt"
COOKIE_WHITELIST_PATH = CONFIG_DIR / "screenshot_web_whitelist_cookie.txt"
SCREENSHOT_DIR = CONFIG_DIR / "screenshots_web"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
PUBLIC_IP_FILE = CONFIG_DIR / "public_ip.env"
FIREFOX_COOKIE_DB = Path(os.getenv("FIREFOX_COOKIE_DB", "")) if os.getenv("FIREFOX_COOKIE_DB") else None
ALLOWED_SCHEMES = {"http", "https"}


def load_allowed_domains() -> list[str]:
    """加载截图访问白名单（仅从 WHITELIST_PATH 读取）。"""
    if not WHITELIST_PATH.exists():
        return []
    domains: list[str] = []
    for line in WHITELIST_PATH.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            domains.append(cleaned)
    return sorted(set(domains))


def load_blocked_domains() -> list[str]:
    if not BLACKLIST_PATH.exists():
        return []
    domains: list[str] = []
    for line in BLACKLIST_PATH.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
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

    if not parsed.netloc:
        raise ValueError("URL must include a hostname")

    return parsed.geturl()


def get_navigation_wait_strategy(url: str) -> tuple[str, int]:
    return "domcontentloaded", 60000


async def navigate_to_page(page, url: str) -> None:
    normalized = normalize_url(url)
    try:
        await page.goto(normalized, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Navigation warning for {normalized}: {exc}")


def _pattern_matches(value: str, pattern: str) -> bool:
    """
    混合匹配：
      1. 如果 pattern 包含 '*'，则作为 glob 模式（使用 fnmatch）进行匹配（忽略大小写）。
      2. 否则，若 value 等于 pattern（忽略大小写），或 value 以 .pattern 结尾（域名后缀匹配），则匹配。
    """
    if not pattern:
        return False
    value_lower = value.lower()
    pattern_lower = pattern.lower()
    if '*' in pattern:
        # 使用 glob 匹配（fnmatch 支持 * 和 ?，但仅用 *）
        return fnmatch(value_lower, pattern_lower)
    else:
        # 精确匹配或后缀匹配
        if value_lower == pattern_lower:
            return True
        if value_lower.endswith("." + pattern_lower):
            return True
        return False


def is_domain_allowed(url: str) -> bool:
    """检查 URL 是否允许截图访问（白名单/黑名单均支持 glob 和后缀匹配）。"""
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()

    # 先检查黑名单
    for pattern in load_blocked_domains():
        if _pattern_matches(normalized, pattern):
            return False
        if hostname and _pattern_matches(hostname, pattern):
            return False
        if scheme and _pattern_matches(scheme, pattern):
            return False

    # 再检查白名单
    for pattern in load_allowed_domains():
        if _pattern_matches(normalized, pattern):
            return True
        if hostname and _pattern_matches(hostname, pattern):
            return True
        if scheme and _pattern_matches(scheme, pattern):
            return True

    return False


# ---------- Cookie 白名单（独立） ----------
def load_cookie_allowed_domains() -> list[str]:
    """只从 COOKIE_WHITELIST_PATH 加载，用于决定是否注入 Cookie。"""
    if not COOKIE_WHITELIST_PATH.exists():
        return []
    domains = []
    for line in COOKIE_WHITELIST_PATH.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            domains.append(cleaned)
    return sorted(set(domains))


def is_cookie_allowed(url: str) -> bool:
    """
    判断是否允许为该 URL 加载 Firefox Cookie。
    仅匹配 hostname（不匹配 scheme 或完整 URL），支持 glob 和后缀匹配。
    """
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False
    for pattern in load_cookie_allowed_domains():
        if _pattern_matches(hostname, pattern):
            return True
    return False
# -------------------------------------------------------


def get_public_ip() -> str:
    try:
        request = Request("https://api.ip.sb/ip", headers={"User-Agent": "curl/8.0"})
        with urlopen(request, timeout=10) as response:
            ip = response.read().decode("utf-8").strip()
        PUBLIC_IP_FILE.parent.mkdir(parents=True, exist_ok=True)
        PUBLIC_IP_FILE.write_text(ip, encoding="utf-8")
        return ip
    except Exception:
        if PUBLIC_IP_FILE.exists():
            cached = PUBLIC_IP_FILE.read_text(encoding="utf-8").strip()
            if cached:
                return cached
        raise


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


def _normalize_cookie_host(hostname: str) -> str:
    cleaned = hostname.strip()
    if not cleaned:
        return ""
    parsed = urlparse(cleaned if "://" in cleaned else f"https://{cleaned}")
    return (parsed.hostname or "").lower()


def _cookie_domain_matches(cookie_host: str, hostname: str) -> bool:
    cookie_host = (cookie_host or "").strip().lower()
    hostname = (hostname or "").strip().lower()
    if not cookie_host or not hostname:
        return False
    if cookie_host.startswith("."):
        domain = cookie_host[1:]
        return hostname == domain or hostname.endswith("." + domain)
    return hostname == cookie_host


def load_firefox_cookies(hostname: str, db_path: Path | None = None) -> list[dict]:
    db_file = db_path or FIREFOX_COOKIE_DB
    if db_file is None:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Firefox cookie DB path is not configured")
        return []
    if not db_file.exists():
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Firefox cookie DB not found: {db_file}")
        return []

    temp_db_path = None
    try:
        if db_path is None:
            temp_dir = Path(tempfile.mkdtemp(prefix="firefox-cookies-", dir=str(CONFIG_DIR)))
            temp_db_path = temp_dir / "cookies.sqlite"
            shutil.copy2(db_file, temp_db_path)
            db_file = temp_db_path

        cookie_hostname = _normalize_cookie_host(hostname)
        if not cookie_hostname:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Empty cookie hostname for input: {hostname!r}")
            return []

        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        # 添加 isHttpOnly 字段
        rows = conn.execute(
            "SELECT host, name, value, path, isSecure, isHttpOnly, expiry FROM moz_cookies"
        ).fetchall()
        conn.close()

        matched = [
            dict(row)
            for row in rows
            if _cookie_domain_matches(row["host"], cookie_hostname)
        ]
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Loaded {len(matched)} cookie(s) for hostname: {hostname} "
            f"(normalized: {cookie_hostname}) out of {len(rows)} total"
        )
        for row in matched:
            print(
                f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] cookie -> host={row['host']} name={row['name']} "
                f"path={row['path']} isSecure={row['isSecure']} isHttpOnly={row.get('isHttpOnly', 0)}"
            )
        return matched
    except Exception as exc:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Failed to load Firefox cookies: {exc}")
        return []
    finally:
        if temp_db_path and temp_db_path.exists():
            shutil.rmtree(temp_db_path.parent, ignore_errors=True)


async def capture_screenshot_bytes(url: str, width: int = 1280, height: int = 720) -> bytes:
    if not (640 <= width <= 1920):
        raise ValueError(f"Width must be between 640 and 1920, got {width}")
    if not (480 <= height <= 1080):
        raise ValueError(f"Height must be between 480 and 1080, got {height}")

    if not is_domain_allowed(url):
        raise ValueError("Target domain is not in the whitelist")

    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""

    from playwright.async_api import async_playwright

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Starting Firefox for {url} with viewport {width}x{height}")
    async with async_playwright() as playwright:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Launching Firefox browser")
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
                "intl.accept_languages": "en-US,en",
                "general.useragent.locale": "en-US",
                "browser.search.region": "US",
                "toolkit.telemetry.enabled": False,
                "datareporting.healthreport.uploadEnabled": False,
                "geo.enabled": False,
                "permissions.default.geo": 0,
                "geo.provider.network.url": "",
                "geo.provider.use_os_location": False,
            },
        )
        context = await browser.new_context(
            viewport={"width": width, "height": height},
            locale="en-US",
            timezone_id="UTC",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"}
        )
        try:
            # Cookie 注入仅当域名在 Cookie 白名单中
            if is_cookie_allowed(normalized):
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Domain is in cookie whitelist, attempting to load Firefox cookies")
                cookies = load_firefox_cookies(hostname)
                if cookies:
                    cookie_payload = []
                    for cookie in cookies:
                        payload = {
                            "name": cookie["name"],
                            "value": cookie["value"],
                            "domain": cookie["host"],
                            "path": cookie["path"] or "/",
                            "secure": bool(cookie.get("isSecure", 0)),
                            "httpOnly": bool(cookie.get("isHttpOnly", 0)),  # 新增
                            "sameSite": "Lax",
                        }
                        expiry = cookie.get("expiry")
                        if isinstance(expiry, (int, float)) and expiry > 0:
                            expiry_seconds = int(expiry / 1000 if expiry > 1_000_000_000_000 else expiry)
                            if expiry_seconds > 0:
                                payload["expires"] = expiry_seconds
                        cookie_payload.append(payload)
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Injecting {len(cookie_payload)} cookie(s) into context for {hostname}")
                    try:
                        await context.add_cookies(cookie_payload)
                    except Exception as exc:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Cookie injection failed: {exc}")
                else:
                    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] No cookies loaded for {hostname}")
            else:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Cookie injection skipped for {hostname} (not in cookie whitelist)")

            page = await context.new_page()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Opening page: {normalized}")
            await navigate_to_page(page, normalized)

            current_url = page.url
            if not is_domain_allowed(current_url):
                error_msg = f"Final URL after redirect '{current_url}' is not allowed"
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] {error_msg}")
                raise ValueError(error_msg)

            try:
                await page.wait_for_load_state("load", timeout=60000)
            except Exception as exc:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Load state warning: {exc}")
            await page.wait_for_timeout(2000)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Page loaded, waiting for final render")
            try:
                public_ip = get_public_ip()
            except Exception as exc:
                print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Failed to resolve public IP, continuing without masking: {exc}")
                public_ip = ""
            if public_ip:
                await mask_ip_in_page(page, public_ip)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Capturing screenshot")
            image_bytes = await page.screenshot(full_page=False)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [screenshot_web] Screenshot captured, size={len(image_bytes)} bytes")
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