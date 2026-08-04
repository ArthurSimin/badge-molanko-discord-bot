# screenshot_security.py
from __future__ import annotations

import ipaddress
import socket
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"

# 白/黑名单文件
WHITELIST_PATH = CONFIG_DIR / "screenshot_web_whitelist.txt"
BLACKLIST_PATH = CONFIG_DIR / "screenshot_web_blacklist.txt"
COOKIE_WHITELIST_PATH = CONFIG_DIR / "screenshot_web_whitelist_cookie.txt"   # 新增

PUBLIC_IP_FILE = CONFIG_DIR / "public_ip.env"

ALLOWED_SCHEMES = {"http", "https"}


# ---------- 辅助：标准化 URL ----------
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


# ---------- 模式匹配（支持通配符 *） ----------
def _pattern_matches(value: str, pattern: str) -> bool:
    if not pattern:
        return False
    value_lower = value.lower()
    pattern_lower = pattern.lower()
    if '*' in pattern:
        return fnmatch(value_lower, pattern_lower)
    else:
        if value_lower == pattern_lower:
            return True
        if value_lower.endswith("." + pattern_lower):
            return True
        return False


# ---------- 白名单 / 黑名单 ----------
def load_allowed_domains() -> list[str]:
    if not WHITELIST_PATH.exists():
        return []
    domains = []
    for line in WHITELIST_PATH.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            domains.append(cleaned)
    return sorted(set(domains))


def load_blocked_domains() -> list[str]:
    if not BLACKLIST_PATH.exists():
        return []
    domains = []
    for line in BLACKLIST_PATH.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            domains.append(cleaned)
    return sorted(set(domains))


def is_domain_allowed(url: str) -> bool:
    """检查 URL 是否通过白名单/黑名单过滤（黑名单优先）"""
    try:
        normalized = normalize_url(url)
    except Exception:
        return False
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()

    # 黑名单
    for pattern in load_blocked_domains():
        if _pattern_matches(normalized, pattern):
            return False
        if hostname and _pattern_matches(hostname, pattern):
            return False
        if scheme and _pattern_matches(scheme, pattern):
            return False

    # 白名单（若为空则默认拒绝）
    for pattern in load_allowed_domains():
        if _pattern_matches(normalized, pattern):
            return True
        if hostname and _pattern_matches(hostname, pattern):
            return True
        if scheme and _pattern_matches(scheme, pattern):
            return True
    return False


# ---------- 私有 IP 检测 ----------
def is_private_ip(ip_str: str) -> bool:
    """检查 IPv4 是否为 RFC1918 私有地址"""
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.version == 4:
            return (ip in ipaddress.ip_network('10.0.0.0/8') or
                    ip in ipaddress.ip_network('172.16.0.0/12') or
                    ip in ipaddress.ip_network('192.168.0.0/16'))
        return False
    except ValueError:
        return True   # 无效 IP 视为不安全


def resolve_ip(hostname: str) -> str:
    """解析主机名，优先返回 IPv4"""
    try:
        addrinfo = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not addrinfo:
            raise ValueError(f"Could not resolve hostname: {hostname}")
        for info in addrinfo:
            if info[0] == socket.AF_INET:
                return info[4][0]
        return addrinfo[0][4][0]
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for {hostname}: {e}")


# ---------- 公网 IP（用于掩码） ----------
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


# ---------- Cookie 白名单 ----------
def load_cookie_allowed_domains() -> list[str]:
    if not COOKIE_WHITELIST_PATH.exists():
        return []
    domains = []
    for line in COOKIE_WHITELIST_PATH.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            domains.append(cleaned)
    return sorted(set(domains))


def is_cookie_allowed(url: str) -> bool:
    """判断是否允许为指定 URL 注入 Cookie（基于 hostname 匹配）"""
    try:
        normalized = normalize_url(url)
        parsed = urlparse(normalized)
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        for pattern in load_cookie_allowed_domains():
            if _pattern_matches(hostname, pattern):
                return True
        return False
    except Exception:
        return False


# ---------- 文本掩码工具（可选） ----------
def mask_ip_in_text(text: str, ip_address: str) -> str:
    if not ip_address or ip_address not in text:
        return text
    return text.replace(ip_address, "**.**.**.**")