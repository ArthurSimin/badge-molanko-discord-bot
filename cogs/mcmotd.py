import asyncio
import base64
import io
import re

import discord
from discord import app_commands
from discord.ext import commands
from mcstatus import JavaServer


class MCMOTDCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # =========================================================
    # MOTD
    # =========================================================

    @staticmethod
    def clean_motd(description) -> str:
        """Convert mcstatus MOTD to plain readable text."""

        if not description:
            return "No MOTD"

        # Some mcstatus versions return an object
        # with to_plain_text().
        if hasattr(description, "to_plain_text"):
            try:
                text = description.to_plain_text()
            except Exception:
                text = str(description)
        else:
            # Some versions return a normal string.
            text = str(description)

        # Remove Minecraft formatting codes.
        text = re.sub(
            r"§[0-9a-fk-or]",
            "",
            text,
            flags=re.IGNORECASE,
        )

        # Normalize newlines.
        text = text.replace("\r", "")

        lines = [
            line.strip()
            for line in text.split("\n")
        ]

        text = "\n".join(lines).strip()

        return text or "No MOTD"

    # =========================================================
    # Server Icon
    # =========================================================

    @staticmethod
    def create_icon_file(icon):
        """
        Convert mcstatus server icon into a Discord File.

        mcstatus usually returns:

        data:image/png;base64,...

        Discord cannot directly use this as an embed URL,
        so we upload it as a Discord attachment.
        """

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

    # =========================================================
    # Slash Command
    # =========================================================

    @app_commands.command(
        name="mcmotd",
        description="Get Minecraft server MOTD, version, and player count",
    )
    @app_commands.allowed_contexts(
        guilds=True,
        dms=True,
        private_channels=True,
    )
    @app_commands.describe(
        server="Minecraft Java server address, e.g. play.example.com:25565"
    )
    async def mcmotd(
        self,
        interaction: discord.Interaction,
        server: str,
    ):
        """Fetch Minecraft Java server status."""

        # =====================================================
        # Validate server address
        # =====================================================

        server = server.strip()

        if not server:
            await interaction.response.send_message(
                "⚠️ Please provide a Minecraft server address.",
                ephemeral=True,
            )
            return

        # Tell Discord that the bot is working.
        await interaction.response.defer(thinking=True)

        # =====================================================
        # Query Minecraft server
        # =====================================================

        try:
            server_obj = JavaServer.lookup(server)

            status = await asyncio.wait_for(
                server_obj.async_status(),
                timeout=10.0,
            )

        except asyncio.TimeoutError:
            await interaction.followup.send(
                f"⏱️ Connection to `{server}` timed out.",
                ephemeral=True,
            )
            return

        except Exception as e:
            error = str(e).strip() or "Unknown error"

            if len(error) > 500:
                error = error[:500] + "..."

            await interaction.followup.send(
                f"⚠️ Failed to query `{server}`.\n"
                f"```text\n{error}\n```",
                ephemeral=True,
            )
            return

        # =====================================================
        # Server information
        # =====================================================

        motd = self.clean_motd(
            status.description
        )

        # Discord Embed field value limit.
        motd = motd[:1024]

        # -----------------------------------------------------
        # Version
        # -----------------------------------------------------

        version = "Unknown"

        if status.version:
            version = getattr(
                status.version,
                "name",
                None,
            ) or "Unknown"

        version = str(version)[:1024]

        # -----------------------------------------------------
        # Players
        # -----------------------------------------------------

        online = getattr(
            status.players,
            "online",
            0,
        )

        max_players = getattr(
            status.players,
            "max",
            0,
        )

        # =====================================================
        # Create Embed
        # =====================================================

        embed = discord.Embed(
            title="Minecraft Server Status",
            description=f"`{server}`",
            color=discord.Color.green(),
        )

        # =====================================================
        # MOTD
        # =====================================================

        embed.add_field(
            name="MOTD",
            value=motd,
            inline=False,
        )

        # =====================================================
        # Version
        # =====================================================

        embed.add_field(
            name="Version",
            value=version,
            inline=True,
        )

        # =====================================================
        # Players
        # =====================================================

        embed.add_field(
            name="Players",
            value=f"{online}/{max_players}",
            inline=True,
        )

        # =====================================================
        # Online player list
        # =====================================================

        try:
            sample = getattr(
                status.players,
                "sample",
                None,
            )

            if sample:
                player_names = []

                for player in sample:
                    name = getattr(
                        player,
                        "name",
                        None,
                    )

                    if name:
                        player_names.append(
                            str(name)
                        )

                if player_names:
                    player_text = ", ".join(
                        player_names
                    )

                    if len(player_text) > 1024:
                        player_text = (
                            player_text[:1021]
                            + "..."
                        )

                    embed.add_field(
                        name="Online Players",
                        value=player_text,
                        inline=False,
                    )

        except Exception:
            pass

        # =====================================================
        # Server Icon
        # =====================================================

        icon = getattr(
            status,
            "icon",
            None,
        )

        icon_file = None

        try:
            icon_file = self.create_icon_file(
                icon
            )

            if icon_file:
                embed.set_thumbnail(
                    url="attachment://server-icon.png"
                )

        except Exception:
            icon_file = None

        # =====================================================
        # Footer
        # =====================================================

        embed.set_footer(
            text="Minecraft Java Edition • mcstatus"
        )

        # =====================================================
        # Send result
        # =====================================================

        try:
            if icon_file:
                await interaction.followup.send(
                    embed=embed,
                    file=icon_file,
                )
            else:
                await interaction.followup.send(
                    embed=embed,
                )

        except discord.HTTPException:
            # If Discord rejects the icon/embed,
            # try sending without the icon.
            try:
                embed._thumbnail = None

                await interaction.followup.send(
                    embed=embed,
                )

            except Exception:
                await interaction.followup.send(
                    "⚠️ Minecraft server was queried successfully, "
                    "but Discord could not display the result.",
                    ephemeral=True,
                )


# =============================================================
# Cog Setup
# =============================================================

async def setup(bot: commands.Bot):
    await bot.add_cog(
        MCMOTDCog(bot)
    )