import discord
from discord import app_commands
from discord.ext import commands
from io import BytesIO

from utils.screenshot import capture_screenshot_bytes, normalize_url


class Screenshot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="screenshot_web", description="Capture a whitelisted web page screenshot at 1280x720")
    @app_commands.allowed_contexts(guilds=True,dms=True,private_channels=True)
    @app_commands.describe(url="Website URL or domain to capture, such as github.com")
    async def screenshot_web(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer(thinking=True)

        try:
            normalized_url = normalize_url(url)
            image_bytes = await capture_screenshot_bytes(normalized_url)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            await interaction.followup.send(f"Screenshot failed: {exc}", ephemeral=True)
            return

        await interaction.followup.send(
            content=f"Captured: {normalized_url}",
            file=discord.File(BytesIO(image_bytes), filename="screenshot.png"),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Screenshot(bot))
