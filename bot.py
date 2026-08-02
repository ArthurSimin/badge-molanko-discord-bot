import discord
from discord.ext import commands
import os
import asyncio
import sys
from dotenv import load_dotenv

# ======================
# Paths
# ======================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ENV_FILE = os.path.join(
    BASE_DIR,
    "discord_bot.env"
)

COGS_DIR = os.path.join(
    BASE_DIR,
    "cogs"
)

# ======================
# Load TOKEN
# ======================

load_dotenv(ENV_FILE)

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError(
        "TOKEN not found in discord_bot.env"
    )

# ======================
# Intents
# ======================

intents = discord.Intents.default()

# ======================
# Bot Class
# ======================

class MyBot(commands.Bot):

    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )
        self._terminal_task = None

    async def setup_hook(self):
        print("Loading cogs...")

        if os.path.exists(COGS_DIR):
            for filename in os.listdir(COGS_DIR):
                if (
                    filename.endswith(".py")
                    and not filename.startswith("_")
                ):
                    extension = f"cogs.{filename[:-3]}"
                    try:
                        await self.load_extension(extension)
                        print(f"Loaded {extension}")
                    except Exception as e:
                        print(f"Failed loading {extension}")
                        print(e)
        else:
            print("cogs folder not found")

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print("Slash sync failed:")
            print(e)

    async def on_ready(self):
        print("========================")
        print(f"Logged in as: {self.user}")
        print(f"ID: {self.user.id}")
        print(f"Servers: {len(self.guilds)}")

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="/time | /version"
        )

        await self.change_presence(
            status=discord.Status.online,
            activity=activity
        )

        print("Bot is ONLINE!")
        print("========================")

        # Start terminal command loop
        self._terminal_task = asyncio.create_task(self.terminal_loop())

    async def terminal_loop(self):
        """Read commands from stdin and execute them."""
        loop = asyncio.get_event_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:  # EOF
                    print("EOF detected, shutting down...")
                    break

                line = line.strip()
                if not line:
                    continue

                parts = line.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else None

                await self.handle_terminal_command(cmd, arg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in terminal loop: {e}")

    async def handle_terminal_command(self, cmd, arg):
        """Dispatch terminal commands."""
        if cmd == "list":
            await self.cmd_list()
        elif cmd == "reload":
            await self.cmd_reload(arg)
        elif cmd == "stop":
            await self.cmd_stop(arg)
        elif cmd == "start":
            await self.cmd_start(arg)
        elif cmd == "help":
            await self.cmd_help()
        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")

    async def cmd_list(self):
        """List loaded cogs and available cogs."""
        loaded = list(self.extensions.keys())
        print(f"Loaded cogs ({len(loaded)}): {', '.join(loaded) if loaded else 'none'}")

        if os.path.exists(COGS_DIR):
            available = [
                f[:-3] for f in os.listdir(COGS_DIR)
                if f.endswith(".py") and not f.startswith("_")
            ]
            print(f"Available cogs: {', '.join(available) if available else 'none'}")
        else:
            print("cogs folder not found")

    async def cmd_reload(self, arg):
        """Reload all cogs, or a specific cog."""
        if arg is None:
            # Reload all: unload all, then load all from directory
            print("Reloading all cogs...")
            for ext in list(self.extensions.keys()):
                try:
                    await self.unload_extension(ext)
                    print(f"Unloaded {ext}")
                except Exception as e:
                    print(f"Failed unloading {ext}: {e}")

            if os.path.exists(COGS_DIR):
                for filename in os.listdir(COGS_DIR):
                    if (
                        filename.endswith(".py")
                        and not filename.startswith("_")
                    ):
                        ext = f"cogs.{filename[:-3]}"
                        try:
                            await self.load_extension(ext)
                            print(f"Loaded {ext}")
                        except Exception as e:
                            print(f"Failed loading {ext}: {e}")
            else:
                print("cogs folder not found")
        else:
            ext = f"cogs.{arg}"
            try:
                await self.reload_extension(ext)
                print(f"Reloaded {ext}")
            except Exception as e:
                print(f"Failed reloading {ext}: {e}")

    async def cmd_stop(self, arg):
        """Stop the bot (if no arg), or unload a specific cog."""
        if arg is None:
            print("Shutting down bot...")
            await self.close()
            asyncio.get_event_loop().stop()
            sys.exit(0)
        else:
            ext = f"cogs.{arg}"
            try:
                await self.unload_extension(ext)
                print(f"Unloaded {ext}")
            except Exception as e:
                print(f"Failed unloading {ext}: {e}")

    async def cmd_start(self, arg):
        """Load a specific cog."""
        if arg is None:
            print("Usage: start <module>")
            return
        ext = f"cogs.{arg}"
        if not os.path.exists(os.path.join(COGS_DIR, f"{arg}.py")):
            print(f"File {arg}.py not found in cogs directory.")
            return
        try:
            await self.load_extension(ext)
            print(f"Loaded {ext}")
        except Exception as e:
            print(f"Failed loading {ext}: {e}")

    async def cmd_help(self):
        """Print available commands."""
        help_text = """
Available terminal commands:
  list                        - Show loaded and available cogs
  reload                      - Unload all cogs and load all from cogs folder
  reload <module>             - Reload a specific cog (without .py)
  stop                        - Shutdown the bot
  stop <module>               - Unload a specific cog
  start <module>              - Load a specific cog
  help                        - Show this help
"""
        print(help_text)

# ======================
# Instantiate bot
# ======================

bot = MyBot()

# ======================
# Error handling
# ======================

@bot.event
async def on_error(event, *args, **kwargs):
    print(f"Error in {event}")

# ======================
# Startup
# ======================

async def main():
    try:
        async with bot:
            await bot.start(TOKEN)
    except discord.LoginFailure:
        print("Invalid TOKEN, please check discord_bot.env")
    except Exception as e:
        print("Bot crashed:")
        print(e)
    finally:
        print("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown by user")