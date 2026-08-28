import asyncio
import platform
import socket

import discord
import psutil
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands
from datetime import datetime, timezone

from utils.i18n import locale_for, t

try:
    import cpuinfo
    CPUINFO_AVAILABLE = True
except ImportError:
    CPUINFO_AVAILABLE = False


class ServerInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="molanko_status",
        description=locale_str(
            "Display server system information including CPU, memory usage and Discord API latency",
            i18n_key="molanko_status.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def molanko_status(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        locale = locale_for(interaction)

        try:
            os_name = platform.system()
            os_release = platform.release()

            # CPU information
            cpu_name = "Unknown"
            arch = platform.machine() or "Unknown"

            if CPUINFO_AVAILABLE:
                try:
                    info = await asyncio.to_thread(cpuinfo.get_cpu_info)
                    cpu_name = info.get("brand_raw", "Unknown")
                    arch = info.get("arch", arch)
                except (PermissionError, OSError):
                    pass

            # psutil information
            try:
                cpu_percent = psutil.cpu_percent(interval=0)
            except (PermissionError, OSError):
                cpu_percent = 0

            try:
                cpu_count = psutil.cpu_count(logical=True)
            except (PermissionError, OSError):
                cpu_count = 0

            try:
                mem = psutil.virtual_memory()
                mem_total = mem.total / (1024 ** 3)
                mem_used = mem.used / (1024 ** 3)
                mem_percent = mem.percent
            except (PermissionError, OSError):
                mem_total = 0
                mem_used = 0
                mem_percent = 0

            # Boot time / uptime
            try:
                boot_timestamp = psutil.boot_time()
                boot_time = datetime.fromtimestamp(
                    boot_timestamp,
                    tz=timezone.utc,
                )
                now = datetime.now(timezone.utc)
                uptime_delta = now - boot_time

                days = uptime_delta.days
                hours, remainder = divmod(uptime_delta.seconds, 3600)
                minutes, _ = divmod(remainder, 60)

                uptime_str = t(
                    "molanko_status.uptime_format",
                    locale=locale,
                    days=days,
                    hours=hours,
                    minutes=minutes,
                )
            except (PermissionError, OSError):
                uptime_str = "Unavailable"

            latency_ms = round(self.bot.latency * 1000)

            response = t(
                "molanko_status.response",
                locale=locale,
                os_name=os_name,
                os_release=os_release,
                uptime=uptime_str,
                cpu_percent=cpu_percent,
                cpu_name=cpu_name,
                arch=arch,
                cpu_count=cpu_count,
                mem_used=f"{mem_used:.2f}",
                mem_total=f"{mem_total:.2f}",
                mem_percent=mem_percent,
                latency_ms=latency_ms,
            )

            await interaction.followup.send(response)

        except Exception as exc:
            await interaction.followup.send(
                t(
                    "molanko_status.error_generic",
                    locale=locale,
                    error=exc,
                )
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerInfo(bot))
