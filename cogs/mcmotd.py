import asyncio
import base64
import io
import re

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands
from mcstatus import JavaServer

from utils.i18n import locale_for, t


class MCMOTDCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def clean_motd(description, no_motd: str = "No MOTD") -> str:
        """Convert mcstatus MOTD to plain readable text."""

        if not description:
            return no_motd

        if hasattr(description, "to_plain_text"):
            try:
                text = description.to_plain_text()
            except Exception:
                text = str(description)
        else:
            text = str(description)

        text = re.sub(
            r"§[0-9a-fk-or]",
            "",
            text,
            flags=re.IGNORECASE,
        )

        text = text.replace("\r", "")

        lines = [line.strip() for line in text.split("\n")]

        text = "\n".join(lines).strip()

        return text or no_motd

    @staticmethod
    def create_icon_file(icon):
        if not icon:
            return None

        if not isinstance(icon, str):
            return None

        try:
            if icon.startswith("data:image/"):
                _, encoded = icon.split(",", 1)
                image_data = base64.b64decode(encoded)
                return discord.File(
                    io.BytesIO(image_data),
                    filename="server-icon.png",
                )
        except Exception:
            return None

        return None

    @app_commands.command(
        name="mcmotd",
        description=locale_str(
            "Get Minecraft server MOTD, version, and player count",
            i18n_key="mcmotd.command_description",
        ),
    )
    @app_commands.allowed_contexts(
        guilds=True,
        dms=True,
        private_channels=True,
    )
    @app_commands.describe(
        server=locale_str(
            "Minecraft Java server address, e.g. play.example.com:25565",
            i18n_key="mcmotd.param.server",
        ),
    )
    async def mcmotd(
        self,
        interaction: discord.Interaction,
        server: str,
    ):
        locale = locale_for(interaction)
        server = server.strip()

        if not server:
            await interaction.response.send_message(
                t("mcmotd.error.empty_address", locale=locale),
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        try:
            server_obj = JavaServer.lookup(server)

            status = await asyncio.wait_for(
                server_obj.async_status(),
                timeout=10.0,
            )

        except asyncio.TimeoutError:
            await interaction.followup.send(
                t("mcmotd.error.timeout", locale=locale, server=server),
                ephemeral=True,
            )
            return

        except Exception as e:
            error = str(e).strip() or t("mcmotd.error.unknown", locale=locale)

            if len(error) > 500:
                error = error[:500] + "..."

            await interaction.followup.send(
                t("mcmotd.error.query_failed", locale=locale, server=server, error=error),
                ephemeral=True,
            )
            return

        no_motd = t("mcmotd.no_motd", locale=locale)
        motd = self.clean_motd(status.description, no_motd=no_motd)
        motd = motd[:1024]

        unknown = t("mcmotd.unknown", locale=locale)
        version = unknown

        if status.version:
            version = getattr(status.version, "name", None) or unknown

        version = str(version)[:1024]

        online = getattr(status.players, "online", 0)
        max_players = getattr(status.players, "max", 0)

        embed = discord.Embed(
            title=t("mcmotd.embed.title", locale=locale),
            description=f"`{server}`",
            color=discord.Color.green(),
        )

        embed.add_field(
            name=t("mcmotd.field.motd", locale=locale),
            value=motd,
            inline=False,
        )

        embed.add_field(
            name=t("mcmotd.field.version", locale=locale),
            value=version,
            inline=True,
        )

        embed.add_field(
            name=t("mcmotd.field.players", locale=locale),
            value=f"{online}/{max_players}",
            inline=True,
        )

        try:
            sample = getattr(status.players, "sample", None)

            if sample:
                player_names = []

                for player in sample:
                    name = getattr(player, "name", None)
                    if name:
                        player_names.append(str(name))

                if player_names:
                    player_text = ", ".join(player_names)

                    if len(player_text) > 1024:
                        player_text = player_text[:1021] + "..."

                    embed.add_field(
                        name=t("mcmotd.field.online_players", locale=locale),
                        value=player_text,
                        inline=False,
                    )

        except Exception:
            pass

        icon = getattr(status, "icon", None)
        icon_file = None

        try:
            icon_file = self.create_icon_file(icon)

            if icon_file:
                embed.set_thumbnail(url="attachment://server-icon.png")

        except Exception:
            icon_file = None

        embed.set_footer(text=t("mcmotd.footer", locale=locale))

        try:
            if icon_file:
                await interaction.followup.send(
                    embed=embed,
                    file=icon_file,
                )
            else:
                await interaction.followup.send(embed=embed)

        except discord.HTTPException:
            try:
                embed._thumbnail = None
                await interaction.followup.send(embed=embed)
            except Exception:
                await interaction.followup.send(
                    t("mcmotd.error.display_failed", locale=locale),
                    ephemeral=True,
                )


async def setup(bot: commands.Bot):
    await bot.add_cog(MCMOTDCog(bot))
