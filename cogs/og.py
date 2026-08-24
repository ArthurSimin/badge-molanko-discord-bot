import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import t
from utils.og import fetch_og_data


class OG(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="og",
        description=locale_str(
            "Fetch Open Graph Protocol metadata from a URL",
            i18n_key="og.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        url=locale_str(
            "The URL to extract Open Graph data from",
            i18n_key="og.param.url",
        ),
    )
    async def og(self, interaction: discord.Interaction, url: str):
        await interaction.response.defer(thinking=True)
        locale = str(interaction.locale) if interaction.locale else None

        try:
            data = await fetch_og_data(url)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            await interaction.followup.send(
                t("og.error.fetch_failed", locale=locale, error=exc),
                ephemeral=True,
            )
            return

        na = t("og.na", locale=locale)
        embed = discord.Embed(
            title=t("og.embed.title", locale=locale),
            color=0x00ccff,
            url=data.get("url") or url,
        )

        image_url = data.get("image")
        if image_url:
            width = data.get("image:width")
            height = data.get("image:height")
            use_thumbnail = True

            if width is not None and height is not None:
                try:
                    w = int(width)
                    h = int(height)
                    if w >= 400 and h >= 400 and w > h and not (0.8 <= w / h <= 1.2):
                        use_thumbnail = False
                except (ValueError, ZeroDivisionError):
                    pass

            if use_thumbnail:
                embed.set_thumbnail(url=image_url)
            else:
                embed.set_image(url=image_url)

        embed.add_field(
            name=t("og.field.title", locale=locale),
            value=data.get("title") or na,
            inline=False,
        )
        embed.add_field(
            name=t("og.field.description", locale=locale),
            value=data.get("description") or na,
            inline=False,
        )
        embed.add_field(
            name=t("og.field.site_name", locale=locale),
            value=data.get("site_name") or na,
            inline=True,
        )
        embed.add_field(
            name=t("og.field.type", locale=locale),
            value=data.get("type") or na,
            inline=True,
        )

        if "image:width" in data and "image:height" in data:
            embed.add_field(
                name=t("og.field.image_size", locale=locale),
                value=f"{data['image:width']}x{data['image:height']}",
                inline=True,
            )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(OG(bot))
