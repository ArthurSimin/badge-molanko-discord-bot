import discord
from discord import app_commands
from discord.ext import commands

class Version(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        version_file = root / "version"
        try:
            self.version = version_file.read_text(encoding="utf-8").strip()
        except Exception:
            self.version = "unknown"

    @app_commands.command(name="version", description="Show the bot version")
    @app_commands.allowed_contexts(guilds=True,dms=True,private_channels=True)
    async def version(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Current version: **{self.version}**")

async def setup(bot: commands.Bot):
    await bot.add_cog(Version(bot))