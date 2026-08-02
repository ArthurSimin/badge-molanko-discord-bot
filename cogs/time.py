import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

class Time(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="time", description="Show the current UTC time")
    @app_commands.allowed_contexts(guilds=True,dms=True,private_channels=True)
    async def time(self, interaction: discord.Interaction):
        now_utc = datetime.now(timezone.utc)
        formatted = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
        await interaction.response.send_message(f"Current UTC time: **{formatted}**")

async def setup(bot: commands.Bot):
    await bot.add_cog(Time(bot))