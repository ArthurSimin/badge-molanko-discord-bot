import asyncio
from io import BytesIO

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import locale_for, t
from utils.mcskin import get_player_image


class MinecraftSkinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="mcskin",
        description=locale_str(
            "Fetch a Minecraft player's face or full skin image",
            i18n_key="mcskin.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        player=locale_str(
            "Minecraft username or UUID (with or without hyphens)",
            i18n_key="mcskin.param.player",
        ),
        image_type=locale_str(
            "Choose face (avatar) or skin (full body)",
            i18n_key="mcskin.param.image_type",
        ),
    )
    @app_commands.choices(
        image_type=[
            app_commands.Choice(
                name=locale_str("Face (avatar)", i18n_key="mcskin.choice.face"),
                value="face",
            ),
            app_commands.Choice(
                name=locale_str("Full Skin", i18n_key="mcskin.choice.skin"),
                value="skin",
            ),
        ]
    )
    async def mcskin(
        self,
        interaction: discord.Interaction,
        player: str,
        image_type: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        locale = locale_for(interaction)

        img_type = image_type.value if image_type else "skin"

        try:
            image_data = await asyncio.to_thread(
                get_player_image,
                player,
                img_type=img_type,
            )
        except ValueError as e:
            await interaction.followup.send(
                t("mcskin.error.invalid_player", locale=locale, error=e),
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(
                t("mcskin.error.fetch_failed", locale=locale, error=e),
                ephemeral=True,
            )
            return

        filename = f"{player}_{img_type}.png"
        file_obj = discord.File(BytesIO(image_data), filename=filename)
        await interaction.followup.send(file=file_obj)


async def setup(bot: commands.Bot):
    await bot.add_cog(MinecraftSkinCog(bot))
