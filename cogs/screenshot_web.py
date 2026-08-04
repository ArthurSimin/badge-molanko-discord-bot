import discord
from discord import app_commands
from discord.ext import commands
from io import BytesIO
from urllib.parse import urlparse

from lanlan3292_python_screenshot_web.firefox import capture_screenshot_bytes, normalize_url
from utils.screenshot_security import (
    is_domain_allowed,
    resolve_ip,
    is_private_ip,
    is_cookie_allowed,
)

# 预设分辨率: (width, height, default_scale)
PRESETS = {
    "480P": (640, 480, 1.0),
    "600P": (800, 600, 1.0),
    "720P": (1280, 720, 1.0),
    "1080P": (1920, 1080, 1.0),
    "2K": (1920, 1080, 1.333334),   # 输出 2560x1440
    "4K": (1920, 1080, 2.0),     # 输出 3840x2160
    "Tor": (1400, 900, 1.0),
}

class Screenshot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="screenshot_web", description="Capture a whitelisted web page screenshot")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        url="Website URL or domain to capture, e.g. github.com",
        width="Width in pixels (640-1920, default 1400) – ignored if preset is set",
        height="Height in pixels (480-1080, default 900) – ignored if preset is set",
        preset="Select a predefined resolution (overrides width/height and optionally scale)",
        full_page="Capture the entire scrollable page (default False)",
        scale="Device pixel ratio (zoom), 0.1-5.0. If not set, preset may choose a suitable value, else 1.0",
        # user_agent="Custom User-Agent string (optional)",   # 已注释
    )
    @app_commands.choices(
        preset=[
            app_commands.Choice(name=name, value=name)
            for name in PRESETS.keys()
        ]
    )
    async def screenshot_web(
        self,
        interaction: discord.Interaction,
        url: str,
        width: int = 1400,
        height: int = 900,
        preset: app_commands.Choice[str] | None = None,
        full_page: bool = False,
        scale: float | None = None,
        # user_agent: str | None = None,   # 已注释
    ):
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

        # 4. 判断是否允许注入 Cookie
        inject_cookies = is_cookie_allowed(normalized_url)

        # 5. 应用预设（覆盖宽高，并可能设置默认 scale）
        if preset:
            preset_name = preset.value
            w, h, preset_scale = PRESETS.get(preset_name, (width, height, 1.0))
            width = w
            height = h
            if scale is None:
                scale = preset_scale
        if scale is None:
            scale = 1.0

        # 6. 执行截图
        try:
            image_bytes, final_url = await capture_screenshot_bytes(
                normalized_url,
                width=width,
                height=height,
                inject_cookies=inject_cookies,
                # user_agent=user_agent,   # 已注释，不传递自定义 UA
                full_page=full_page,
                device_scale_factor=scale,
            )
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            await interaction.followup.send(f"Screenshot failed: {exc}", ephemeral=True)
            return

        output_width = int((width * scale))
        output_height = int((height * scale))

        # 7. 发送结果
        content_parts = [
            f"**URL:** {final_url}",
            f"**Viewport:** {width}x{height}",
            f"**Output resolution:** {output_width}x{output_height}",
            f"**Full page:** {full_page}",
            f"**Scale:** {scale}",
        ]
        # if user_agent:   # 已注释
        #     content_parts.append(f"**User-Agent:** {user_agent}")
        content = "\n".join(content_parts)

        await interaction.followup.send(
            content=content,
            file=discord.File(BytesIO(image_bytes), filename="screenshot.png"),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Screenshot(bot))