import discord
from discord import app_commands
from discord.ext import commands

from utils.og import fetch_og_data


class OG(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="og", description="Fetch Open Graph Protocol metadata from a URL")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(url="The URL to extract Open Graph data from")
    async def og(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer(thinking=True)

        try:
            data = await fetch_og_data(url)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            await interaction.followup.send(f"Failed to fetch OG data: {exc}", ephemeral=True)
            return

        # 构建 Embed 展示元数据
        embed = discord.Embed(
            title="Open Graph Metadata",
            color=0x00ccff,
            url=data.get("url") or url
        )
        embed.set_thumbnail(url=data.get("image") or None)

        embed.add_field(name="Title", value=data.get("title") or "N/A", inline=False)
        embed.add_field(name="Description", value=data.get("description") or "N/A", inline=False)
        embed.add_field(name="Site Name", value=data.get("site_name") or "N/A", inline=True)
        embed.add_field(name="Type", value=data.get("type") or "N/A", inline=True)

        if "image:width" in data and "image:height" in data:
            embed.add_field(
                name="Image Size",
                value=f"{data['image:width']}×{data['image:height']}",
                inline=True
            )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(OG(bot))