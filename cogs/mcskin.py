import asyncio
from io import BytesIO

import discord
from discord import app_commands
from discord.ext import commands

from utils.mcskin import get_player_image


class MinecraftSkinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="mcskin",
        description="Fetch a Minecraft player's face or full skin image"
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        player="Minecraft username or UUID (with or without hyphens)",
        image_type="Choose 'face' (avatar) or 'skin' (full body)"
    )
    @app_commands.choices(
        image_type=[
            app_commands.Choice(name="Face (avatar)", value="face"),
            app_commands.Choice(name="Full Skin", value="skin")
        ]
    )
    async def mcskin(
        self,
        interaction: discord.Interaction,
        player: str,
        image_type: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(thinking=True)

        # 若未提供，默认使用 "skin"
        img_type = image_type.value if image_type else "skin"

        try:
            # utils.mcskin 使用 urllib.request，是同步阻塞 I/O。
            # 放到线程池，避免 DNS/HTTP 卡住 Discord.py 的事件循环。
            image_data = await asyncio.to_thread(
                get_player_image,
                player,
                img_type=img_type,
            )
        except ValueError as e:
            await interaction.followup.send(
                f"Invalid player identifier: {e}",
                ephemeral=True
            )
            return
        except Exception as e:
            await interaction.followup.send(
                f"Failed to retrieve image: {e}",
                ephemeral=True
            )
            return

        filename = f"{player}_{img_type}.png"
        file_obj = discord.File(BytesIO(image_data), filename=filename)
        await interaction.followup.send(file=file_obj)


async def setup(bot: commands.Bot):
    await bot.add_cog(MinecraftSkinCog(bot))
