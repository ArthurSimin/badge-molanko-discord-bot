import uuid

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import t


class UUID(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="uuid",
        description=locale_str(
            "Generate a UUID v4",
            i18n_key="uuid.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def uuid(self, interaction: discord.Interaction):
        generated = uuid.uuid4()
        await interaction.response.send_message(f"{generated}")


async def setup(bot: commands.Bot):
    await bot.add_cog(UUID(bot))
