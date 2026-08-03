import asyncio
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

# 复用已有的 URL 规范化、IP 解析和私有 IP 检查函数
from utils.screenshot import normalize_url, resolve_ip, is_private_ip


async def fetch_og_data(url: str) -> dict:
    """
    获取指定 URL 的 Open Graph 元数据。
    返回字典，包含 title, description, image, site_name, type 等键。
    若遇非法输入、私有 IP 或请求失败，抛出 ValueError。
    """
    normalized = normalize_url(url)

    # 解析主机名，拒绝 RFC1918 私有 IPv4（防止 SSRF）
    parsed = urlparse(normalized)
    hostname = parsed.hostname or ""
    if hostname:
        try:
            ip = resolve_ip(hostname)
            if is_private_ip(ip):
                raise ValueError(f"Access to private IP address is not allowed (resolved {hostname} -> {ip})")
        except Exception as e:
            raise ValueError(f"DNS/private IP check failed: {e}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; Molankobot/1.0)"
        )
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(normalized, headers=headers, timeout=15, allow_redirects=True) as resp:
                resp.raise_for_status()
                final_url = str(resp.url)
                html = await resp.text()
        except aiohttp.ClientError as e:
            raise ValueError(f"Failed to fetch page: {e}")
        except asyncio.TimeoutError:
            raise ValueError("Request timed out")

    # 使用 BeautifulSoup 解析 HTML
    soup = BeautifulSoup(html, "html.parser")
    og_data = {}

    # 提取所有 <meta property="og:...">
    for meta in soup.find_all("meta", property=True):
        prop = meta.get("property")
        if prop and prop.startswith("og:"):
            key = prop[3:]  # 去掉 "og:"
            content = meta.get("content")
            if content:
                og_data[key] = content

    # 回退到 <title> 和 <meta name="description">
    if "title" not in og_data:
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            og_data["title"] = title_tag.string.strip()

    if "description" not in og_data:
        desc_meta = soup.find("meta", attrs={"name": "description"})
        if desc_meta and desc_meta.get("content"):
            og_data["description"] = desc_meta.get("content")

    # 确保 image URL 为绝对路径
    if "image" in og_data and og_data["image"]:
        og_data["image"] = urljoin(final_url, og_data["image"])

    # 记录最终 URL（跟随重定向后）
    og_data["url"] = final_url

    return og_data