import discord
from discord import app_commands
from discord.ext import commands

class Version(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.version = "1.2.0"

    @app_commands.command(name="version", description="Show the bot version")
    async def version(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Current version: **{self.version}**")

async def setup(bot: commands.Bot):
    await bot.add_cog(Version(bot))