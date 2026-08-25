import asyncio
import json
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import locale_for, t


# 自定义异常
class AvatarProcessingError(Exception):
    pass


async def fetch_skin_from_username(username: str) -> bytes:
    """从 Mojang API 获取玩家皮肤图片"""
    async with aiohttp.ClientSession() as session:
        # 1. 获取 UUID
        async with session.get(
            f"https://api.mojang.com/users/profiles/minecraft/{username}"
        ) as resp:
            if resp.status != 200:
                raise ValueError(f"Player '{username}' not found")
            data = await resp.json()
            uuid = data["id"]

        # 2. 获取皮肤 URL
        async with session.get(
            f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
        ) as resp:
            if resp.status != 200:
                raise ValueError("Failed to fetch profile")
            profile = await resp.json()
            # 查找 texture 属性
            textures = next(
                (prop for prop in profile["properties"] if prop["name"] == "textures"),
                None,
            )
            if not textures:
                raise ValueError("No textures found in profile")
            import base64
            decoded = base64.b64decode(textures["value"]).decode("utf-8")
            import json as jsonlib
            texture_data = jsonlib.loads(decoded)
            skin_url = texture_data["textures"]["SKIN"]["url"]

        # 3. 下载皮肤
        async with session.get(skin_url) as resp:
            if resp.status != 200:
                raise ValueError("Failed to download skin")
            return await resp.read()


async def process_skin_nodejs(image_data: bytes, options: dict) -> bytes:
    """调用 Node.js 脚本处理皮肤图片"""
    script_path = Path(__file__).parent.parent / "scripts" / "process_avatar.js"
    if not script_path.exists():
        raise FileNotFoundError(f"Node.js script not found at {script_path}")

    options_json = json.dumps(options)

    proc = await asyncio.create_subprocess_exec(
        "node",
        str(script_path),
        options_json,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate(input=image_data)

    if proc.returncode != 0:
        error_msg = stderr.decode().strip() or "Unknown Node.js error"
        raise AvatarProcessingError(f"Node.js processing failed: {error_msg}")

    return stdout


class MinecraftAvatarCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="mcavatar",
        description=locale_str(
            "Generate a pixel-style Minecraft avatar with optional effects",
            i18n_key="mcavatar.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        player=locale_str(
            "Minecraft username to use (optional if image is provided)",
            i18n_key="mcavatar.param.player",
        ),
        image=locale_str(
            "Skin image attachment (optional if player is provided)",
            i18n_key="mcavatar.param.image",
        ),
        scale=locale_str(
            "Final upscale factor (default 10)",
            i18n_key="mcavatar.param.scale",
        ),
        outline=locale_str(
            "Outline pixel width: 0=off, 1=1px, 2=2px",
            i18n_key="mcavatar.param.outline",
        ),
        outline_color=locale_str(
            "Outline color: auto / auto_darker / auto_lighter or hex (#000000)",
            i18n_key="mcavatar.param.outline_color",
        ),
        bg_color=locale_str(
            "Background color: auto / auto_lighter / auto_darker or hex (#ffffff)",
            i18n_key="mcavatar.param.bg_color",
        ),
        fill_background=locale_str(
            "Whether to fill the background",
            i18n_key="mcavatar.param.fill_background",
        ),
        upscale48=locale_str(
            "Upscale to 48x48 scaling",
            i18n_key="mcavatar.param.upscale48",
        ),
        average_color=locale_str(
            "Average color for auto outline/bg: hex (#ff0000) or auto",
            i18n_key="mcavatar.param.average_color",
        ),
    )
    @app_commands.choices(
        outline=[
            app_commands.Choice(
                name=locale_str("Off", i18n_key="mcavatar.choice.outline_off"),
                value=0,
            ),
            app_commands.Choice(
                name=locale_str("1px", i18n_key="mcavatar.choice.outline_1px"),
                value=1,
            ),
            app_commands.Choice(
                name=locale_str("2px", i18n_key="mcavatar.choice.outline_2px"),
                value=2,
            ),
        ]
    )
    async def mcavatar(
        self,
        interaction: discord.Interaction,
        player: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
        scale: int = 10,
        outline: int = 2,
        outline_color: str = "auto",
        bg_color: str = "auto",
        fill_background: bool = True,
        upscale48: bool = True,
        average_color: Optional[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        locale = locale_for(interaction)

        if not player and not image:
            await interaction.followup.send(
                t("mcavatar.error.need_player_or_image", locale=locale),
                ephemeral=True,
            )
            return

        try:
            if image:
                if not image.content_type or not image.content_type.startswith("image/"):
                    await interaction.followup.send(
                        t("mcavatar.error.invalid_image", locale=locale),
                        ephemeral=True,
                    )
                    return
                image_data = await image.read()
            else:
                image_data = await fetch_skin_from_username(player)
        except Exception as e:
            await interaction.followup.send(
                t("mcavatar.error.fetch_skin", locale=locale, error=e),
                ephemeral=True,
            )
            return

        options = {
            "scale": scale,
            "outlineMode": outline,
            "outlineColor": outline_color,
            "bgColor": bg_color,
            "fillBackground": fill_background,
            "upscale48": upscale48,
        }

        if average_color:
            if average_color.lower() == "auto":
                pass
            else:
                try:
                    hex_str = average_color.lstrip("#")
                    if len(hex_str) == 3:
                        hex_str = "".join(c * 2 for c in hex_str)
                    if len(hex_str) != 6:
                        raise ValueError("Invalid hex length")
                    r = int(hex_str[0:2], 16)
                    g = int(hex_str[2:4], 16)
                    b = int(hex_str[4:6], 16)
                    options["averageColor"] = {"r": r, "g": g, "b": b}
                except Exception:
                    await interaction.followup.send(
                        t("mcavatar.error.invalid_average_color", locale=locale),
                        ephemeral=True,
                    )
                    return

        try:
            result_data = await process_skin_nodejs(image_data, options)
        except AvatarProcessingError as e:
            await interaction.followup.send(
                t("mcavatar.error.processing", locale=locale, error=e),
                ephemeral=True,
            )
            return
        except FileNotFoundError:
            await interaction.followup.send(
                t("mcavatar.error.script_not_found", locale=locale),
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(
                t("mcavatar.error.unexpected", locale=locale, error=e),
                ephemeral=True,
            )
            return

        file = discord.File(BytesIO(result_data), filename="avatar.png")
        player_display = player or t("mcavatar.attachment_label", locale=locale)
        await interaction.followup.send(
            content=t(
                "mcavatar.success",
                locale=locale,
                player=player_display,
            ),
            file=file,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MinecraftAvatarCog(bot))
