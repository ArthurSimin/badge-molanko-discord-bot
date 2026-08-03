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

        embed = discord.Embed(
            title="Open Graph Metadata",
            color=0x00ccff,
            url=data.get("url") or url
        )

        # ---------- 智能选择图片显示方式 ----------
        image_url = data.get("image")
        if image_url:
            width = data.get("image:width")
            height = data.get("image:height")
            use_thumbnail = True  # 默认缩略图

            if width is not None and height is not None:
                try:
                    w = int(width)
                    h = int(height)
                    # 大图条件：宽≥400、高≥400、横屏、非方形
                    if w >= 400 and h >= 400 and w > h and not (0.8 <= w / h <= 1.2):
                        use_thumbnail = False
                except (ValueError, ZeroDivisionError):
                    pass  # 尺寸无效，保持缩略图

            if use_thumbnail:
                embed.set_thumbnail(url=image_url)
            else:
                embed.set_image(url=image_url)

        # ---------- 元数据字段 ----------
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