import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands
from pathlib import Path

from utils.i18n import locale_for, t


class Version(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        root = Path(__file__).resolve().parents[1]
        version_file = root / "version"
        try:
            self.version = version_file.read_text(encoding="utf-8").strip()
        except Exception:
            self.version = "unknown"

    @app_commands.command(
        name="version",
        description=locale_str(
            "Show the bot version",
            i18n_key="version.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def version(self, interaction: discord.Interaction):
        locale = locale_for(interaction)
        message = t("version.response", locale=locale, version=self.version)
        await interaction.response.send_message(message)


async def setup(bot: commands.Bot):
    await bot.add_cog(Version(bot))
