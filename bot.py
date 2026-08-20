import asyncio
import datetime
import logging
import os
import sys
import traceback

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from terminal_commands import TerminalCommandHandler


logging.basicConfig(level=logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, "discord_bot.env")
COGS_DIR = os.path.join(BASE_DIR, "cogs")
UTILS_DIR = os.path.join(BASE_DIR, "utils")

load_dotenv(ENV_FILE)
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN not found in discord_bot.env")

intents = discord.Intents.default()


def log_message(msg: str) -> None:
    """Print a timestamped log message to the console."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")


class MyBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix="!", intents=intents)
        self.cogs_dir = COGS_DIR
        self.utils_dir = UTILS_DIR
        self.cmd_handler = TerminalCommandHandler(self)
        self._terminal_task: asyncio.Task | None = None

    async def setup_hook(self) -> None:
        """Load extensions and start background tasks once per Bot instance."""
        await self._load_cogs()

        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception:
            logging.exception("Slash command sync failed")

        # setup_hook runs once per Bot instance. on_ready may run repeatedly
        # when Discord reconnects, so background tasks should not start there.
        self._terminal_task = asyncio.create_task(
            self.terminal_loop(),
            name="terminal-loop",
        )

    async def _load_cogs(self) -> None:
        print("Loading cogs...")
        if not os.path.isdir(self.cogs_dir):
            print("cogs folder not found")
            return

        for filename in sorted(os.listdir(self.cogs_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            extension = f"cogs.{filename[:-3]}"
            try:
                await self.load_extension(extension)
                print(f"Loaded {extension}")
            except Exception:
                logging.exception("Failed loading %s", extension)

    async def terminal_loop(self) -> None:
        """Read terminal commands without blocking Discord's event loop."""
        while True:
            try:
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line:
                    print("EOF detected, stopping terminal loop")
                    return

                line = line.strip()
                if not line:
                    continue

                parts = line.split(maxsplit=1)
                command = parts[0].lower()
                argument = parts[1] if len(parts) > 1 else None
                await self.cmd_handler.dispatch(command, argument)

            except asyncio.CancelledError:
                return
            except Exception:
                logging.exception("Error in terminal loop")

    async def close(self) -> None:
        """Cancel the terminal task before closing the Discord client."""
        terminal_task = self._terminal_task
        self._terminal_task = None

        if terminal_task and not terminal_task.done():
            if terminal_task is not asyncio.current_task():
                terminal_task.cancel()
                try:
                    await terminal_task
                except asyncio.CancelledError:
                    pass
            else:
                terminal_task.cancel()

        await super().close()

    async def on_ready(self) -> None:
        print("========================")
        print(f"Logged in as: {self.user}")
        print(f"ID: {self.user.id}")
        print(f"Servers: {len(self.guilds)}")

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="/time | /version",
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

        print("Bot is ONLINE!")
        print("========================")

    async def on_command(self, ctx: commands.Context) -> None:
        log_message(
            f"Command invoked by {ctx.author} (ID: {ctx.author.id}) "
            f"with command '{ctx.command.qualified_name}'"
        )

    async def on_app_command_completion(
        self,
        interaction: discord.Interaction,
        command: app_commands.Command,
    ) -> None:
        """Log successful application command execution without overriding dispatch."""
        log_message(
            f"Application command '{command.qualified_name}' invoked by "
            f"{interaction.user} (ID: {interaction.user.id})"
        )

    async def on_error(self, event: str, *args, **kwargs) -> None:
        print(f"Unhandled error in {event}:")
        traceback.print_exc()

    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        command_name = getattr(interaction.command, "name", "unknown")
        log_message(
            f"ERROR in command '{command_name}' invoked by "
            f"{interaction.user}: {error}"
        )
        traceback.print_exception(type(error), error, error.__traceback__)

        if not interaction.response.is_done():
            try:
                await interaction.response.send_message(
                    "❌ 命令执行出错，请查看控制台日志。\n"
                    f"错误类型：{type(error).__name__}",
                    ephemeral=True,
                )
            except Exception:
                logging.exception("Failed to send application command error")


async def main() -> None:
    max_retries = 5
    retry_delay = 5

    for attempt in range(1, max_retries + 1):
        bot = MyBot()
        try:
            async with bot:
                await bot.start(TOKEN)
            return
        except discord.LoginFailure:
            print("Invalid TOKEN, please check discord_bot.env")
            return
        except Exception:
            logging.exception(
                "Connection attempt %s/%s failed",
                attempt,
                max_retries,
            )

            if attempt == max_retries:
                print("Max retries reached. Exiting.")
                return

            print(f"Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            retry_delay *= 2


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown by user")
