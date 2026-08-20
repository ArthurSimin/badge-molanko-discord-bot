import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from io import BytesIO
from urllib.parse import urlparse
import math

from lanlan3292_python_screenshot_web.firefox import capture_screenshot_bytes, normalize_url
from utils.screenshot_security import (
    is_domain_allowed,
    resolve_ip_async,
    is_blocked_destination_ip,
    is_cookie_allowed,
    is_fullpage_allowed,
    should_block_media,
)

PRESETS = {
    "480P": (640, 480, 1.0),
    "600P": (800, 600, 1.0),
    "720P": (1280, 720, 1.0),
    "1080P": (1920, 1080, 1.0),
    "2K": (1920, 1080, 1.333334),
    "4K": (1920, 1080, 2.0),
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
        block_media="Force blocking of images/videos? If True, always block; if False or not set, use default policy.",
    )
    @app_commands.choices(
        preset=[app_commands.Choice(name=name, value=name) for name in PRESETS.keys()]
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
        block_media: bool | None = None,
    ):
        await interaction.response.defer(thinking=True)

        try:
            normalized_url = normalize_url(url)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        try:
            allowed = await asyncio.to_thread(is_domain_allowed, normalized_url)
            if not allowed:
                await interaction.followup.send(
                    "This domain is not allowed by the whitelist/blacklist policy.",
                    ephemeral=True,
                )
                return

            parsed = urlparse(normalized_url)
            hostname = parsed.hostname
            if not hostname:
                await interaction.followup.send("Invalid URL: no hostname found.", ephemeral=True)
                return

            ip = await resolve_ip_async(hostname)
            if is_blocked_destination_ip(ip):
                await interaction.followup.send(
                    f"Access to private IP addresses is not allowed (resolved {hostname} -> {ip})",
                    ephemeral=True,
                )
                return

            inject_cookies = await asyncio.to_thread(is_cookie_allowed, normalized_url)

            if preset:
                preset_name = preset.value
                width, height, preset_scale = PRESETS.get(preset_name, (width, height, 1.0))
                if scale is None:
                    scale = preset_scale
            if scale is None:
                scale = 1.0

            default_block = await asyncio.to_thread(should_block_media, normalized_url)
            final_block = block_media is True or default_block

            image_bytes, final_url = await capture_screenshot_bytes(
                normalized_url,
                width=width,
                height=height,
                inject_cookies=inject_cookies,
                full_page=full_page,
                device_scale_factor=scale,
                block_media=final_block,
            )

            final_allowed = await asyncio.to_thread(is_domain_allowed, final_url)
            if not final_allowed:
                await interaction.followup.send(
                    f"Redirected URL '{final_url}' is not allowed by whitelist/blacklist policy.",
                    ephemeral=True,
                )
                return

            if full_page:
                fullpage_allowed = await asyncio.to_thread(is_fullpage_allowed, final_url)
                if not fullpage_allowed:
                    await interaction.followup.send(
                        f"Full-page screenshot is not allowed for '{final_url}'. Please use a domain from the full-page whitelist.",
                        ephemeral=True,
                    )
                    return

            parsed_final = urlparse(final_url)
            final_hostname = parsed_final.hostname
            if final_hostname:
                final_ip = await resolve_ip_async(final_hostname)
                if is_blocked_destination_ip(final_ip):
                    await interaction.followup.send(
                        f"Redirected URL resolved to private IP address: {final_hostname} -> {final_ip}",
                        ephemeral=True,
                    )
                    return

        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            await interaction.followup.send(f"Screenshot failed: {exc}", ephemeral=True)
            return

        def get_image_size(data: bytes) -> tuple[int, int]:
            from PIL import Image
            with Image.open(BytesIO(data)) as img:
                return img.size

        output_width, output_height = await asyncio.to_thread(get_image_size, image_bytes)

        content_parts = [
            f"**URL:** {final_url}",
            f"**Viewport:** {width}x{height}",
            f"**Output resolution:** {output_width}x{output_height}",
        ]
        if not math.isclose(float(scale), 1.0):
            content_parts.append(f"**Scale:** {scale}")
        if full_page:
            content_parts.append(f"**Full page:** {full_page}")
        if final_block:
            content_parts.append(f"**Block Media:** {final_block}")

        await interaction.followup.send(
            content="\n".join(content_parts),
            file=discord.File(BytesIO(image_bytes), filename="screenshot.png"),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Screenshot(bot))
