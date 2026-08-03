import platform
import socket
import psutil
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

# Try to import cpuinfo for detailed CPU info
try:
    import cpuinfo
    CPUINFO_AVAILABLE = True
except ImportError:
    CPUINFO_AVAILABLE = False


class ServerInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="server_info",
        description="Display server system information including CPU, memory usage and Discord API latency"
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def server_info(self, interaction: discord.Interaction):
        # Defer to avoid timeout while gathering system info
        await interaction.response.defer(thinking=True)

        try:
            # System info
            os_name = platform.system()
            os_release = platform.release()
            hostname = socket.gethostname()

            # CPU name and architecture (if available)
            if CPUINFO_AVAILABLE:
                info = cpuinfo.get_cpu_info()
                cpu_name = info.get('brand_raw', 'Unknown')
                arch = info.get('arch', 'Unknown')
            else:
                cpu_name = 'Unknown'
                arch = 'Unknown'

            # CPU usage and core count
            cpu_percent = psutil.cpu_percent(interval=0)
            cpu_count = psutil.cpu_count(logical=True)

            # Memory
            mem = psutil.virtual_memory()
            mem_total = mem.total / (1024 ** 3)   # GB
            mem_used = mem.used / (1024 ** 3)
            mem_percent = mem.percent

            # Uptime
            boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
            now = datetime.now(timezone.utc)
            uptime_delta = now - boot_time
            days = uptime_delta.days
            hours, remainder = divmod(uptime_delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            uptime_str = f"{days}d {hours}h {minutes}m"

            # Discord API latency (in milliseconds)
            latency_ms = round(self.bot.latency * 1000)

            # Build response
            response = (
                f"**Server Information**\n"
                #f" Hostname: {hostname}\n"
                f"OS: {os_name} {os_release}\n"
                f"Uptime: {uptime_str}\n"
                f"CPU: {cpu_percent}% - {cpu_name}\n"
                f"Architecture: {arch}, {cpu_count} cores\n"
                f"Memory: {mem_used:.2f} GB / {mem_total:.2f} GB ({mem_percent}%)\n"
                f"Discord API Latency: {latency_ms} ms"
            )

            await interaction.followup.send(response)

        except ImportError:
            await interaction.followup.send(
                "The `psutil` library is not installed. Please install it to use this command."
            )
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerInfo(bot))