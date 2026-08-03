import asyncio
import datetime
import time
import urllib.robotparser
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from utils.screenshot import normalize_url, resolve_ip, is_private_ip

# ---------- 日志函数 ----------
def log_message(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [og] {msg}")

# ---------- 常量配置 ----------
USER_AGENT = "Mozilla/5.0 (compatible; Molankobot/1.0)"
DEFAULT_TIMEOUT = 15
ROBOTS_TIMEOUT = 5
MAX_RESPONSE_SIZE = 5 * 1024 * 1024
MAX_REDIRECTS = 10
ROBOTS_CACHE_TTL = 300
ROBOTS_CACHE_MAX_SIZE = 2000
MAX_RETRIES = 3

_robots_cache = {}


async def _check_host(url: str) -> None:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Invalid URL: missing hostname")
    try:
        ip = await asyncio.to_thread(resolve_ip, hostname)
        if is_private_ip(ip):
            raise ValueError(f"Private IP not allowed: {hostname} -> {ip}")
    except Exception as e:
        raise ValueError(f"DNS/private IP check failed: {e}")


async def _get_robots_parser(session: aiohttp.ClientSession, domain: str):
    now = time.time()
    if len(_robots_cache) >= ROBOTS_CACHE_MAX_SIZE:
        _robots_cache.clear()

    if domain in _robots_cache:
        timestamp, rp = _robots_cache[domain]
        if now - timestamp < ROBOTS_CACHE_TTL:
            return rp

    robots_url = f"{domain}/robots.txt" if domain.startswith(("http://", "https://")) else f"https://{domain}/robots.txt"
    await _check_host(robots_url)

    rp = urllib.robotparser.RobotFileParser()
    try:
        async with session.get(
            robots_url,
            timeout=aiohttp.ClientTimeout(total=ROBOTS_TIMEOUT),
            allow_redirects=False,
        ) as resp:
            if resp.status == 200:
                content = await resp.text()
                rp.parse(content.splitlines())
    except Exception:
        pass

    _robots_cache[domain] = (now, rp)
    return rp


async def _check_robots_txt(session: aiohttp.ClientSession, url: str) -> bool:
    parsed = urlparse(url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    rp = await _get_robots_parser(session, domain)
    return rp.can_fetch(USER_AGENT, url)


async def fetch_og_data(url: str) -> dict:
    """
    获取指定 URL 的 Open Graph 和 Twitter Card 元数据。
    若数据不完整（缺少 title/description/image）或网络错误，最多重试 MAX_RETRIES 次。
    """
    log_message(f"Starting fetch for URL: {url}")

    last_result = None
    last_exception = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log_message(f"Attempt {attempt}/{MAX_RETRIES}")
            result = await _fetch_og_data_once(url)

            # 检查数据完整性：若 title、description、image 都缺失，视为不完整
            has_title = bool(result.get("title"))
            has_desc = bool(result.get("description"))
            has_image = bool(result.get("image"))

            if has_title or has_desc or has_image:
                # 数据完整，返回
                log_message("Data complete, returning")
                return result
            else:
                # 数据不完整，记录结果并重试
                log_message("Data incomplete, will retry")
                last_result = result
                continue
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_exception = e
            log_message(f"Attempt {attempt} failed with network error: {e}, retrying...")
            continue
        except ValueError as e:
            # 安全错误直接抛出
            raise
        except Exception as e:
            last_exception = e
            log_message(f"Attempt {attempt} failed with unexpected error: {e}, retrying...")
            continue

    # 所有尝试都失败或不完整
    if last_result is not None:
        # 返回最后一次获取的结果（即使不完整）
        log_message("Returning incomplete data after all retries")
        return last_result
    else:
        raise ValueError(f"All retries failed. Last error: {last_exception}")


async def _fetch_og_data_once(url: str) -> dict:
    """单次尝试获取 OG 数据，不含重试逻辑"""
    normalized = normalize_url(url)
    log_message(f"Normalized URL: {normalized}")

    # 1. 初始 IP 检查
    await _check_host(normalized)

    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession() as session:
        # 2. robots.txt 检查
        if not await _check_robots_txt(session, normalized):
            raise ValueError("Access to this URL is disallowed by robots.txt")

        current_url = normalized
        final_html = None
        final_url = None

        for redirect_count in range(MAX_REDIRECTS + 1):
            async with session.get(
                current_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT),
                allow_redirects=False,
            ) as resp:
                if 300 <= resp.status < 400:
                    location = resp.headers.get("Location")
                    if not location:
                        raise ValueError("Redirect response missing Location header")
                    next_url = urljoin(current_url, location)
                    log_message(f"Redirect to: {next_url}")

                    await _check_host(next_url)
                    if not await _check_robots_txt(session, next_url):
                        raise ValueError("robots.txt disallows the redirected URL")

                    current_url = next_url
                    continue

                # 最终响应
                content_type = resp.headers.get("Content-Type", "").lower()
                if not ("text/html" in content_type or "application/xhtml+xml" in content_type):
                    raise ValueError(f"Response is not HTML (Content-Type: {resp.headers.get('Content-Type', 'unknown')})")

                content_length = resp.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        cl = int(content_length)
                        if cl > MAX_RESPONSE_SIZE:
                            raise ValueError(f"Content-Length exceeds limit ({cl} > {MAX_RESPONSE_SIZE} bytes)")
                    except ValueError:
                        pass

                chunk = await resp.content.read(MAX_RESPONSE_SIZE + 1)
                if len(chunk) > MAX_RESPONSE_SIZE:
                    raise ValueError("Response too large (exceeds 5 MiB)")

                charset = resp.charset or "utf-8"
                final_html = chunk.decode(charset, errors="replace")
                final_url = str(resp.url)
                log_message(f"Fetched HTML, size: {len(final_html)} bytes, URL: {final_url}")
                break
        else:
            raise ValueError("Too many redirects")

        # 3. 解析 HTML
        soup = await asyncio.to_thread(BeautifulSoup, final_html, "html.parser")
        log_message("HTML parsed with BeautifulSoup")

        og_data = {}

        # 提取 Open Graph
        for meta in soup.find_all("meta", property=True):
            prop = meta.get("property")
            if prop and prop.startswith("og:"):
                key = prop[3:]
                content = meta.get("content")
                if content:
                    og_data[key] = content

        log_message(f"Extracted OG data: {og_data}")

        # 提取 Twitter Card
        twitter_data = {}
        for meta in soup.find_all("meta", attrs={"name": lambda x: x and x.startswith("twitter:")}):
            name = meta.get("name")
            if name:
                key = name[8:]
                content = meta.get("content")
                if content:
                    twitter_data[key] = content

        log_message(f"Extracted Twitter data: {twitter_data}")

        # 合并 Twitter → OG（若 OG 缺失）
        if "title" not in og_data and "title" in twitter_data:
            og_data["title"] = twitter_data["title"]
        if "description" not in og_data and "description" in twitter_data:
            og_data["description"] = twitter_data["description"]
        if "image" not in og_data and "image" in twitter_data:
            og_data["image"] = twitter_data["image"]
        if "card" in twitter_data:
            og_data["twitter_card"] = twitter_data["card"]

        # 回退到 <title> 和 <meta name="description">
        if "title" not in og_data:
            title_tag = soup.find("title")
            if title_tag and title_tag.string:
                og_data["title"] = title_tag.string.strip()

        if "description" not in og_data:
            desc_meta = soup.find("meta", attrs={"name": "description"})
            if desc_meta and desc_meta.get("content"):
                og_data["description"] = desc_meta.get("content")

        # 图片 URL 转为绝对路径
        if "image" in og_data and og_data["image"]:
            og_data["image"] = urljoin(final_url, og_data["image"])

        og_data["url"] = final_url

        log_message(f"Final OG data: {og_data}")
        return og_data