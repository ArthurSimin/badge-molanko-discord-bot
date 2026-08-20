# screenshot_security.py
from __future__ import annotations

import asyncio
import ipaddress
import socket
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"

WHITELIST_PATH = CONFIG_DIR / "screenshot_web_whitelist.txt"
BLACKLIST_PATH = CONFIG_DIR / "screenshot_web_blacklist.txt"
COOKIE_WHITELIST_PATH = CONFIG_DIR / "screenshot_web_whitelist_cookie.txt"
FULLPAGE_WHITELIST_PATH = CONFIG_DIR / "screenshot_web_fullpage_whitelist.txt"
PUBLIC_IP_FILE = CONFIG_DIR / "public_ip.env"

ALLOWED_SCHEMES = {"http", "https"}


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


def _pattern_matches(value: str, pattern: str) -> bool:
    if not pattern:
        return False
    value_lower = value.lower()
    pattern_lower = pattern.lower()
    if '*' in pattern:
        return fnmatch(value_lower, pattern_lower)
    return (
        value_lower == pattern_lower
        or value_lower.endswith("." + pattern_lower)
    )


def load_allowed_domains() -> list[str]:
    if not WHITELIST_PATH.exists():
        return []
    return sorted({
        line.strip()
        for line in WHITELIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    })


def load_blocked_domains() -> list[str]:
    if not BLACKLIST_PATH.exists():
        return []
    return sorted({
        line.strip()
        for line in BLACKLIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    })


def is_domain_allowed(url: str) -> bool:
    try:
        normalized = normalize_url(url)
    except Exception:
        return False
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()

    for pattern in load_blocked_domains():
        if _pattern_matches(normalized, pattern) or _pattern_matches(hostname, pattern):
            return False

    for pattern in load_allowed_domains():
        if _pattern_matches(normalized, pattern) or _pattern_matches(hostname, pattern):
            return True
    return False


def is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        # Reject all non-public addresses, including loopback/link-local/reserved
        # and IPv6 private/ULA addresses, not only RFC1918 IPv4 ranges.
        return not ip.is_global
    except ValueError:
        return True


def resolve_ip(hostname: str) -> str:
    try:
        addrinfo = socket.getaddrinfo(
            hostname,
            None,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM,
        )
        if not addrinfo:
            raise ValueError(f"Could not resolve hostname: {hostname}")
        # Prefer IPv4, preserving existing behavior when both families exist.
        for info in addrinfo:
            if info[0] == socket.AF_INET:
                return info[4][0]
        return addrinfo[0][4][0]
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for {hostname}: {e}") from e


async def resolve_ip_async(hostname: str) -> str:
    """Resolve DNS without blocking Discord.py's event loop."""
    return await asyncio.to_thread(resolve_ip, hostname)


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


async def get_public_ip_async() -> str:
    """Fetch public IP without blocking Discord.py's event loop."""
    return await asyncio.to_thread(get_public_ip)


def load_cookie_allowed_domains() -> list[str]:
    if not COOKIE_WHITELIST_PATH.exists():
        return []
    return sorted({
        line.strip()
        for line in COOKIE_WHITELIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    })


def is_cookie_allowed(url: str) -> bool:
    try:
        normalized = normalize_url(url)
        hostname = (urlparse(normalized).hostname or "").lower()
        if not hostname:
            return False
        return any(_pattern_matches(hostname, pattern) for pattern in load_cookie_allowed_domains())
    except Exception:
        return False


def load_fullpage_allowed_domains() -> list[str]:
    if not FULLPAGE_WHITELIST_PATH.exists():
        return []
    return sorted({
        line.strip()
        for line in FULLPAGE_WHITELIST_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    })


def is_fullpage_allowed(url: str) -> bool:
    try:
        normalized = normalize_url(url)
        hostname = (urlparse(normalized).hostname or "").lower()
        if not hostname:
            return False
        return any(_pattern_matches(hostname, pattern) for pattern in load_fullpage_allowed_domains())
    except Exception:
        return False


def mask_ip_in_text(text: str, ip_address: str) -> str:
    if not ip_address or ip_address not in text:
        return text
    return text.replace(ip_address, "**.**.**.**")


BLOCK_MEDIA_PATH = CONFIG_DIR / "screenshot_web_block_media.txt"


def load_block_media_patterns() -> list[str]:
    if not BLOCK_MEDIA_PATH.exists():
        return []
    return sorted({
        line.strip()
        for line in BLOCK_MEDIA_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    })


def should_block_media(url: str) -> bool:
    if not url:
        return False
    url_lower = url.lower()
    return any(fnmatch(url_lower, pattern.lower()) for pattern in load_block_media_patterns())
