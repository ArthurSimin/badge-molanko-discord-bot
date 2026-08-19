import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from mcstatus import JavaServer

class MCMOTDCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="mcmotd",
        description="Get Minecraft server MOTD, version, and player count"
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        server="Server address (e.g., play.example.com:25565 or just play.example.com)"
    )
    async def mcmotd(self, interaction: discord.Interaction, server: str):
        """Fetch and display MOTD, version, and online players of a Minecraft Java server."""
        await interaction.response.defer(thinking=True)

        try:
            server_obj = JavaServer.lookup(server)
            # 使用 asyncio.wait_for 控制整体超时
            status = await asyncio.wait_for(server_obj.async_status(), timeout=10.0)
        except asyncio.TimeoutError:
            await interaction.followup.send(
                f"⏱️ Connection to `{server}` timed out.",
                ephemeral=True
            )
            return
        except Exception as e:
            await interaction.followup.send(
                f"⚠️ Failed to query server `{server}`: {e}",
                ephemeral=True
            )
            return

        # 提取信息
        motd = status.description.to_plain_text() if status.description else "No MOTD"
        version = status.version.name if status.version else "Unknown"
        online = status.players.online
        max_players = status.players.max

        embed = discord.Embed(
            title=f"🖥️ Server Status: {server}",
            color=discord.Color.green()
        )
        embed.add_field(name="MOTD", value=motd, inline=False)
        embed.add_field(name="Version", value=version, inline=True)
        embed.add_field(name="Players", value=f"{online}/{max_players}", inline=True)

        # 尝试获取 ping（同样用 asyncio.wait_for）
        try:
            ping = await asyncio.wait_for(server_obj.async_ping(), timeout=5.0)
            embed.add_field(name="Ping", value=f"{int(ping)}ms", inline=True)
        except Exception:
            pass  # ping 失败则忽略

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(MCMOTDCog(bot))