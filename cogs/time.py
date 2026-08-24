from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import t


class Time(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="time",
        description=locale_str(
            "Show the current UTC time",
            i18n_key="time.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def time(self, interaction: discord.Interaction):
        locale = str(interaction.locale) if interaction.locale else None
        now_utc = datetime.now(timezone.utc)
        formatted = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        await interaction.response.send_message(
            t("time.response", locale=locale, time=formatted)
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Time(bot))
