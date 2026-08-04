import discord
from discord import app_commands
from discord.ext import commands
from io import BytesIO
from urllib.parse import urlparse

# 导入拆分后的模块
from utils.screenshot_web_firefox import capture_screenshot_bytes, normalize_url
from utils.screenshot_security import (
    is_domain_allowed,
    resolve_ip,
    is_private_ip,
    is_cookie_allowed,
)


class Screenshot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="screenshot_web", description="Capture a whitelisted web page screenshot at specified resolution")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        url="Website URL or domain to capture, such as github.com",
        width="Width in pixels (640-1920, default 1280)",
        height="Height in pixels (480-1080, default 720)"
    )
    async def screenshot_web(self, interaction: discord.Interaction, url: str, width: int = 1280, height: int = 720):
        await interaction.response.defer(thinking=True)

        # 1. 标准化 URL
        try:
            normalized_url = normalize_url(url)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        # 2. 域名白名单/黑名单检查
        try:
            if not is_domain_allowed(normalized_url):
                await interaction.followup.send(
                    "This domain is not allowed by the whitelist/blacklist policy.",
                    ephemeral=True
                )
                return
        except Exception as exc:
            await interaction.followup.send(f"Security policy check failed: {exc}", ephemeral=True)
            return

        # 3. 私有 IP 检查（解析主机名）
        parsed = urlparse(normalized_url)
        hostname = parsed.hostname
        if not hostname:
            await interaction.followup.send("Invalid URL: no hostname found.", ephemeral=True)
            return

        try:
            ip = resolve_ip(hostname)
            if is_private_ip(ip):
                await interaction.followup.send(
                    f"Access to private IP addresses is not allowed (resolved {hostname} -> {ip})",
                    ephemeral=True
                )
                return
        except Exception as exc:
            await interaction.followup.send(f"DNS resolution or private IP check failed: {exc}", ephemeral=True)
            return

        # 4. 判断是否允许注入 Cookie（根据 Cookie 白名单）
        inject_cookies = is_cookie_allowed(normalized_url)

        # 5. 执行截图（无额外安全检查）
        try:
            image_bytes = await capture_screenshot_bytes(
                normalized_url,
                width,
                height,
                inject_cookies=inject_cookies
            )
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            await interaction.followup.send(f"Screenshot failed: {exc}", ephemeral=True)
            return

        # 6. 发送结果
        await interaction.followup.send(
            content=f"Captured: {normalized_url} ({width}x{height})",
            file=discord.File(BytesIO(image_bytes), filename="screenshot.png"),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Screenshot(bot))