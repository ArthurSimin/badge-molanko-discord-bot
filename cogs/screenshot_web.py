import asyncio
import math
from io import BytesIO
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from lanlan3292_python_screenshot_web.firefox import capture_screenshot_bytes, normalize_url
from utils.i18n import locale_for, t
from utils.screenshot_security import (
    is_blocked_destination_ip,
    is_cookie_allowed,
    is_domain_allowed,
    is_fullpage_allowed,
    resolve_ip_async,
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

    @app_commands.command(
        name="screenshot_web",
        description=locale_str(
            "Capture a whitelisted web page screenshot",
            i18n_key="screenshot_web.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        url=locale_str(
            "Website URL or domain to capture, e.g. github.com",
            i18n_key="screenshot_web.param.url",
        ),
        width=locale_str(
            "Width in px 640-1920 (default 1400); ignored if preset set",
            i18n_key="screenshot_web.param.width",
        ),
        height=locale_str(
            "Height in px 480-1080 (default 900); ignored if preset set",
            i18n_key="screenshot_web.param.height",
        ),
        preset=locale_str(
            "Predefined resolution (overrides width/height, optional scale)",
            i18n_key="screenshot_web.param.preset",
        ),
        full_page=locale_str(
            "Capture the entire scrollable page (default False)",
            i18n_key="screenshot_web.param.full_page",
        ),
        scale=locale_str(
            "Device pixel ratio 0.1-5.0; preset may set default",
            i18n_key="screenshot_web.param.scale",
        ),
        block_media=locale_str(
            "Force block images/videos; else use default policy",
            i18n_key="screenshot_web.param.block_media",
        ),
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
        locale = locale_for(interaction)

        try:
            normalized_url = normalize_url(url)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        try:
            allowed = await asyncio.to_thread(is_domain_allowed, normalized_url)
            if not allowed:
                await interaction.followup.send(
                    t("screenshot_web.error.domain_not_allowed", locale=locale),
                    ephemeral=True,
                )
                return

            parsed = urlparse(normalized_url)
            hostname = parsed.hostname
            if not hostname:
                await interaction.followup.send(
                    t("screenshot_web.error.no_hostname", locale=locale),
                    ephemeral=True,
                )
                return

            ip = await resolve_ip_async(hostname)
            if is_blocked_destination_ip(ip):
                await interaction.followup.send(
                    t(
                        "screenshot_web.error.private_ip",
                        locale=locale,
                        hostname=hostname,
                        ip=ip,
                    ),
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
                    t(
                        "screenshot_web.error.redirect_not_allowed",
                        locale=locale,
                        url=final_url,
                    ),
                    ephemeral=True,
                )
                return

            if full_page:
                fullpage_allowed = await asyncio.to_thread(is_fullpage_allowed, final_url)
                if not fullpage_allowed:
                    await interaction.followup.send(
                        t(
                            "screenshot_web.error.fullpage_not_allowed",
                            locale=locale,
                            url=final_url,
                        ),
                        ephemeral=True,
                    )
                    return

            parsed_final = urlparse(final_url)
            final_hostname = parsed_final.hostname
            if final_hostname:
                final_ip = await resolve_ip_async(final_hostname)
                if is_blocked_destination_ip(final_ip):
                    await interaction.followup.send(
                        t(
                            "screenshot_web.error.redirect_private_ip",
                            locale=locale,
                            hostname=final_hostname,
                            ip=final_ip,
                        ),
                        ephemeral=True,
                    )
                    return

        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            await interaction.followup.send(
                t("screenshot_web.error.failed", locale=locale, error=exc),
                ephemeral=True,
            )
            return

        def get_image_size(data: bytes) -> tuple[int, int]:
            from PIL import Image

            with Image.open(BytesIO(data)) as img:
                return img.size

        output_width, output_height = await asyncio.to_thread(get_image_size, image_bytes)

        content_parts = [
            t("screenshot_web.result.url", locale=locale, url=final_url),
            t(
                "screenshot_web.result.viewport",
                locale=locale,
                width=width,
                height=height,
            ),
            t(
                "screenshot_web.result.output",
                locale=locale,
                width=output_width,
                height=output_height,
            ),
        ]
        if not math.isclose(float(scale), 1.0):
            content_parts.append(
                t("screenshot_web.result.scale", locale=locale, scale=scale)
            )
        if full_page:
            content_parts.append(
                t("screenshot_web.result.full_page", locale=locale, full_page=full_page)
            )
        if final_block:
            content_parts.append(
                t(
                    "screenshot_web.result.block_media",
                    locale=locale,
                    block_media=final_block,
                )
            )

        await interaction.followup.send(
            content="\n".join(content_parts),
            file=discord.File(BytesIO(image_bytes), filename="screenshot.png"),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Screenshot(bot))
