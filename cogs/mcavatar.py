import asyncio
import json
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

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

    # 将选项转为 JSON 字符串
    options_json = json.dumps(options)

    # 启动子进程
    proc = await asyncio.create_subprocess_exec(
        "node",
        str(script_path),
        options_json,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 传递图片数据，等待完成
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
        description="Generate a pixel-style Minecraft avatar with optional effects"
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        player="Minecraft username to use (optional if image is provided)",
        image="Skin image attachment (optional if player is provided)",
        scale="Final upscale factor (default 10)",
        outline="Outline pixel width: 0=off, 1=1px, 2=2px",
        outline_color="Outline color: auto_dark / auto_darker / auto_medium_dark or hex (#000000)",
        bg_color="Background color: auto_light / auto_lighter / auto_medium_light or hex (#ffffff)",
        fill_background="Whether to fill the background",
        upscale48="Upscale to 48x48 scaling",
        average_color="Override the average color used for auto outline/bg. Hex color code (e.g. #ff0000) or 'auto' for automatic."
    )
    @app_commands.choices(
        outline=[
            app_commands.Choice(name="Off", value=0),
            app_commands.Choice(name="1px", value=1),
            app_commands.Choice(name="2px", value=2),
        ]
    )
    async def mcavatar(
        self,
        interaction: discord.Interaction,
        player: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
        scale: int = 10,
        outline: int = 2,
        outline_color: str = "auto_dark",
        bg_color: str = "auto_light",
        fill_background: bool = True,
        upscale48: bool = True,
        average_color: Optional[str] = None,
    ):
        await interaction.response.defer(thinking=True)

        # 至少提供 player 或 image
        if not player and not image:
            await interaction.followup.send(
                "You must provide either a player name or an image attachment.",
                ephemeral=True
            )
            return

        # 获取皮肤图片数据
        try:
            if image:
                if not image.content_type or not image.content_type.startswith("image/"):
                    await interaction.followup.send("Invalid image attachment.", ephemeral=True)
                    return
                image_data = await image.read()
            else:
                image_data = await fetch_skin_from_username(player)
        except Exception as e:
            await interaction.followup.send(f"Failed to get skin image: {e}", ephemeral=True)
            return

        # 构建 Node.js 选项
        options = {
            "scale": scale,
            "outlineMode": outline,
            "outlineColor": outline_color,
            "bgColor": bg_color,
            "fillBackground": fill_background,
            "upscale48": upscale48,
        }

        # 处理 average_color
        if average_color:
            if average_color.lower() == "auto":
                # 明确指定 auto 时，不传递 averageColor，让 Node.js 自动计算
                pass
            else:
                # 解析十六进制颜色
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
                        "Invalid average_color format. Use hex like #ff0000 or #f00.",
                        ephemeral=True
                    )
                    return

        # 调用 Node.js 处理
        try:
            result_data = await process_skin_nodejs(image_data, options)
        except AvatarProcessingError as e:
            await interaction.followup.send(f"Processing failed: {e}", ephemeral=True)
            return
        except FileNotFoundError as e:
            await interaction.followup.send(
                "Internal error: Node.js script not found. Please contact admin.",
                ephemeral=True
            )
            return
        except Exception as e:
            await interaction.followup.send(f"Unexpected error: {e}", ephemeral=True)
            return

        # 发送结果
        file = discord.File(BytesIO(result_data), filename="avatar.png")
        player_display = player or "attachment"
        await interaction.followup.send(
            content=f"✅ Avatar generated for **{player_display}**",
            file=file
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(MinecraftAvatarCog(bot))