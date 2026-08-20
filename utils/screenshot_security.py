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

# RFC 2544 reserves 198.18.0.0/15 for network benchmarking. Proxy clients
# commonly use this range as synthetic/fake DNS addresses. These addresses
# are not routable destinations themselves; the configured proxy resolves
# the original hostname when the browser connects.
PROXY_SYNTHETIC_NETWORKS = (
    ipaddress.ip_network("198.18.0.0/15"),
)


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
    if "*" in pattern:
        return fnmatch(value_lower, pattern_lower)
    return value_lower == pattern_lower or value_lower.endswith("." + pattern_lower)


def _load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted({
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    })


def load_allowed_domains() -> list[str]:
    return _load_lines(WHITELIST_PATH)


def load_blocked_domains() -> list[str]:
    return _load_lines(BLACKLIST_PATH)


def is_domain_allowed(url: str) -> bool:
    try:
        normalized = normalize_url(url)
    except Exception:
        return False
    hostname = (urlparse(normalized).hostname or "").lower()

    for pattern in load_blocked_domains():
        if _pattern_matches(normalized, pattern) or _pattern_matches(hostname, pattern):
            return False

    return any(
        _pattern_matches(normalized, pattern) or _pattern_matches(hostname, pattern)
        for pattern in load_allowed_domains()
    )


def is_proxy_synthetic_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in network for network in PROXY_SYNTHETIC_NETWORKS)


def is_private_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return not ip.is_global
    except ValueError:
        return True


def is_blocked_destination_ip(ip_str: str) -> bool:
    """Return True when the resolved address must be blocked by SSRF checks."""
    return is_private_ip(ip_str) and not is_proxy_synthetic_ip(ip_str)


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
        for info in addrinfo:
            if info[0] == socket.AF_INET:
                return info[4][0]
        return addrinfo[0][4][0]
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {hostname}: {exc}") from exc


async def resolve_ip_async(hostname: str) -> str:
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
    return await asyncio.to_thread(get_public_ip)


def load_cookie_allowed_domains() -> list[str]:
    return _load_lines(COOKIE_WHITELIST_PATH)


def is_cookie_allowed(url: str) -> bool:
    try:
        hostname = (urlparse(normalize_url(url)).hostname or "").lower()
        return bool(hostname) and any(_pattern_matches(hostname, p) for p in load_cookie_allowed_domains())
    except Exception:
        return False


def load_fullpage_allowed_domains() -> list[str]:
    return _load_lines(FULLPAGE_WHITELIST_PATH)


def is_fullpage_allowed(url: str) -> bool:
    try:
        hostname = (urlparse(normalize_url(url)).hostname or "").lower()
        return bool(hostname) and any(_pattern_matches(hostname, p) for p in load_fullpage_allowed_domains())
    except Exception:
        return False


def mask_ip_in_text(text: str, ip_address: str) -> str:
    return text.replace(ip_address, "**.**.**.**") if ip_address and ip_address in text else text


BLOCK_MEDIA_PATH = CONFIG_DIR / "screenshot_web_block_media.txt"


def load_block_media_patterns() -> list[str]:
    return _load_lines(BLOCK_MEDIA_PATH)


def should_block_media(url: str) -> bool:
    if not url:
        return False
    value = url.lower()
    return any(fnmatch(value, pattern.lower()) for pattern in load_block_media_patterns())
