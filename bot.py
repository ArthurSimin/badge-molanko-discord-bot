import discord
from discord.ext import commands
import os
import asyncio
import sys
import shutil
import importlib
import gc
from dotenv import load_dotenv

# ======================
# Paths
# ======================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ENV_FILE = os.path.join(BASE_DIR, "discord_bot.env")
COGS_DIR = os.path.join(BASE_DIR, "cogs")
UTILS_DIR = os.path.join(BASE_DIR, "utils")

# ======================
# Load TOKEN
# ======================

load_dotenv(ENV_FILE)
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN not found in discord_bot.env")

# ======================
# Intents
# ======================

intents = discord.Intents.default()

# ======================
# Bot Class
# ======================

class MyBot(commands.Bot):

    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self._terminal_task = None
        self._shutdown = False

    async def setup_hook(self):
        print("Loading cogs...")

        if os.path.exists(COGS_DIR):
            for filename in os.listdir(COGS_DIR):
                # Only load .py files (not .py.disabled)
                if filename.endswith(".py") and not filename.startswith("_"):
                    extension = f"cogs.{filename[:-3]}"
                    try:
                        await self.load_extension(extension)
                        print(f"Loaded {extension}")
                    except Exception as e:
                        print(f"Failed loading {extension}: {e}")
        else:
            print("cogs folder not found")

        # Sync slash commands
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print("Slash sync failed:", e)

    async def on_ready(self):
        print("========================")
        print(f"Logged in as: {self.user}")
        print(f"ID: {self.user.id}")
        print(f"Servers: {len(self.guilds)}")

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="/time | /version"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)

        print("Bot is ONLINE!")
        print("========================")

        # Start terminal command loop
        self._terminal_task = asyncio.create_task(self.terminal_loop())

    async def terminal_loop(self):
        """Read commands from stdin and execute them."""
        loop = asyncio.get_event_loop()
        while not self._shutdown:
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
        elif cmd == "load":
            await self.cmd_load(arg)
        elif cmd == "disable":
            await self.cmd_disable(arg)
        elif cmd == "enable":
            await self.cmd_enable(arg)
        elif cmd == "sync":
            await self.cmd_sync()
        elif cmd == "help":
            await self.cmd_help()
        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")

    # ---------- Helper methods ----------

    def _get_cog_files(self):
        """
        Return a dict: {cog_name: {'file': full_path, 'disabled': bool}}
        - For .py files, name = filename[:-3]
        - For .py.disabled files, name = filename[:-12] (removes '.py.disabled')
        """
        result = {}
        if not os.path.exists(COGS_DIR):
            return result

        for filename in os.listdir(COGS_DIR):
            if filename.startswith("_"):
                continue
            if filename.endswith(".py"):
                name = filename[:-3]  # remove '.py'
                result[name] = {
                    "file": os.path.join(COGS_DIR, filename),
                    "disabled": False
                }
            elif filename.endswith(".py.disabled"):
                # remove the entire '.py.disabled' suffix (12 characters)
                name = filename[:-12]
                result[name] = {
                    "file": os.path.join(COGS_DIR, filename),
                    "disabled": True
                }
        return result

    def _is_loaded(self, cog_name):
        """Check if a cog (e.g. 'cogs.foo') is currently loaded."""
        return f"cogs.{cog_name}" in self.extensions

    def _clear_cog_cache(self, cog_name):
        """
        Thoroughly remove all traces of a cog from memory and disk cache.
        """
        # 1. Remove module(s) from sys.modules
        module_prefix = f"cogs.{cog_name}"
        to_remove = [mod for mod in list(sys.modules.keys()) if mod == module_prefix or mod.startswith(module_prefix + ".")]
        for mod in to_remove:
            del sys.modules[mod]
            print(f"Removed {mod} from sys.modules")

        # 2. Force garbage collection to free any circular references
        gc.collect()
        print("Ran garbage collection")

        # 3. Delete __pycache__ directory for that cog
        cog_file_path = self._get_cog_files().get(cog_name, {}).get("file")
        if cog_file_path and os.path.exists(cog_file_path):
            pycache_dir = os.path.join(os.path.dirname(cog_file_path), "__pycache__")
            if os.path.exists(pycache_dir):
                try:
                    shutil.rmtree(pycache_dir)
                    print(f"Deleted {pycache_dir}")
                except Exception as e:
                    print(f"Failed to delete {pycache_dir}: {e}")
        # 4. Invalidate importlib caches
        importlib.invalidate_caches()
        print("Invalidated importlib caches")

    def _clear_utils_cache(self):
        """
        Remove all utils modules from sys.modules and delete __pycache__ folders.
        """
        if not os.path.exists(UTILS_DIR):
            print("utils directory not found, skipping")
            return

        # 1. Remove utils modules from sys.modules
        to_remove = [mod for mod in list(sys.modules.keys()) if mod.startswith("utils.")]
        for mod in to_remove:
            del sys.modules[mod]
            print(f"Removed {mod} from sys.modules")

        # 2. Delete all __pycache__ folders under utils
        for root, dirs, files in os.walk(UTILS_DIR):
            if "__pycache__" in dirs:
                pycache_path = os.path.join(root, "__pycache__")
                try:
                    shutil.rmtree(pycache_path)
                    print(f"Deleted {pycache_path}")
                except Exception as e:
                    print(f"Failed to delete {pycache_path}: {e}")

        # 3. Invalidate importlib caches
        importlib.invalidate_caches()
        print("Invalidated importlib caches for utils")

    # ---------- Command implementations ----------

    async def cmd_list(self):
        """List all cog files with their status."""
        cog_info = self._get_cog_files()
        if not cog_info:
            print("No cog files found.")
            return

        print("Cog status:")
        for name, info in sorted(cog_info.items()):
            loaded = self._is_loaded(name)
            disabled = info["disabled"]
            status = []
            status.append("loaded" if loaded else "unloaded")
            status.append("disabled" if disabled else "enabled")
            print(f"  {name}: {', '.join(status)}")

    async def cmd_reload(self, arg):
        """
        Deep reload: unload, clear caches, delete __pycache__, then load.
        Also syncs slash commands after reload.
        If arg is None or "utils", reloads all cogs and utils modules.
        If arg is a cog name, reloads only that cog.
        """
        # Treat "utils" as reload all
        if arg == "utils":
            arg = None

        if arg is None:
            # Full reload: all cogs + utils
            print("Reloading all cogs and utils...")
            cog_info = self._get_cog_files()
            enabled_cogs = [name for name, info in cog_info.items() if not info["disabled"]]

            # 1. Unload all loaded cogs
            for name in enabled_cogs:
                ext = f"cogs.{name}"
                if self._is_loaded(name):
                    try:
                        await self.unload_extension(ext)
                        print(f"Unloaded {ext}")
                    except Exception as e:
                        print(f"Failed unloading {ext}: {e}")

            # 2. Clear caches for all cogs
            for name in enabled_cogs:
                self._clear_cog_cache(name)

            # 3. Clear utils cache
            self._clear_utils_cache()

            # 4. Load all cogs
            for name in enabled_cogs:
                ext = f"cogs.{name}"
                try:
                    await self.load_extension(ext)
                    print(f"Loaded {ext}")
                except Exception as e:
                    print(f"Failed loading {ext}: {e}")

            # 5. Sync slash commands
            try:
                synced = await self.tree.sync()
                print(f"Re-synced {len(synced)} slash command(s)")
            except Exception as e:
                print(f"Slash sync after reload failed: {e}")

        else:
            # Reload a specific cog only (utils are NOT cleared)
            cog_info = self._get_cog_files()
            if arg not in cog_info:
                print(f"Cog '{arg}' not found.")
                return
            if cog_info[arg]["disabled"]:
                print(f"Cog '{arg}' is disabled. Enable it first.")
                return

            ext = f"cogs.{arg}"
            if self._is_loaded(arg):
                try:
                    await self.unload_extension(ext)
                    print(f"Unloaded {ext}")
                except Exception as e:
                    print(f"Failed unloading {ext}: {e}")

            self._clear_cog_cache(arg)

            try:
                await self.load_extension(ext)
                print(f"Loaded {ext}")
            except Exception as e:
                print(f"Failed loading {ext}: {e}")

            # Sync after reload
            try:
                synced = await self.tree.sync()
                print(f"Re-synced {len(synced)} slash command(s)")
            except Exception as e:
                print(f"Slash sync after reload failed: {e}")

    async def cmd_stop(self, arg):
        """Stop the bot (no arg), or unload a specific cog."""
        if arg is None:
            # Graceful shutdown
            print("Shutting down bot...")
            self._shutdown = True
            if self._terminal_task and not self._terminal_task.done():
                self._terminal_task.cancel()
                try:
                    await self._terminal_task
                except asyncio.CancelledError:
                    pass
            await self.close()
            # The main loop will exit naturally
        else:
            ext = f"cogs.{arg}"
            if arg not in self._get_cog_files():
                print(f"Cog '{arg}' not found.")
                return
            if not self._is_loaded(arg):
                print(f"Cog '{arg}' is not loaded.")
                return
            try:
                await self.unload_extension(ext)
                print(f"Unloaded {ext}")
            except Exception as e:
                print(f"Failed unloading {ext}: {e}")

    async def cmd_load(self, arg):
        """Load a specific cog (must be enabled, i.e., not .disabled)."""
        if arg is None:
            print("Usage: load <module>")
            return

        cog_info = self._get_cog_files()
        if arg not in cog_info:
            print(f"Cog '{arg}' not found.")
            return
        if cog_info[arg]["disabled"]:
            print(f"Cog '{arg}' is disabled. Use 'enable {arg}' first.")
            return
        if self._is_loaded(arg):
            print(f"Cog '{arg}' is already loaded.")
            return

        ext = f"cogs.{arg}"
        try:
            await self.load_extension(ext)
            print(f"Loaded {ext}")
            # Optionally sync after loading
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"Failed loading {ext}: {e}")

    async def cmd_disable(self, arg):
        """Unload a cog and rename its file to .py.disabled."""
        if arg is None:
            print("Usage: disable <module>")
            return

        cog_info = self._get_cog_files()
        if arg not in cog_info:
            print(f"Cog '{arg}' not found.")
            return
        if cog_info[arg]["disabled"]:
            print(f"Cog '{arg}' is already disabled.")
            return

        # Unload if loaded
        if self._is_loaded(arg):
            ext = f"cogs.{arg}"
            try:
                await self.unload_extension(ext)
                print(f"Unloaded {ext}")
            except Exception as e:
                print(f"Failed unloading {ext}: {e}")
                return

        # Rename file: .py -> .py.disabled
        old_path = cog_info[arg]["file"]
        new_path = old_path + ".disabled"
        try:
            os.rename(old_path, new_path)
            print(f"Disabled '{arg}' (renamed to {os.path.basename(new_path)})")
        except Exception as e:
            print(f"Failed to disable {arg}: {e}")

    async def cmd_enable(self, arg):
        """
        Remove .disabled suffix from a cog file (rename .py.disabled -> .py).
        Does NOT load the cog automatically.
        """
        if arg is None:
            print("Usage: enable <module>")
            return

        cog_info = self._get_cog_files()
        if arg not in cog_info:
            print(f"Cog '{arg}' not found.")
            return
        if not cog_info[arg]["disabled"]:
            print(f"Cog '{arg}' is already enabled.")
            return

        old_path = cog_info[arg]["file"]
        if not old_path.endswith(".py.disabled"):
            print(f"Internal error: {old_path} does not end with .py.disabled")
            return
        new_path = old_path[:-12] + ".py"   # remove '.py.disabled' and add '.py'
        try:
            os.rename(old_path, new_path)
            print(f"Enabled '{arg}' (renamed to {os.path.basename(new_path)})")
        except Exception as e:
            print(f"Failed to enable {arg}: {e}")

        # Do NOT load the cog automatically

    async def cmd_sync(self):
        """Manually sync slash commands."""
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"Slash sync failed: {e}")

    async def cmd_help(self):
        """Print available commands."""
        help_text = """
Available terminal commands:
  list                        - Show all cogs with status (loaded/unloaded, enabled/disabled)
  reload                      - Deep reload all cogs and utils (clears cache, __pycache__, GC)
  reload utils                - Same as reload (all cogs + utils)
  reload <module>             - Deep reload a specific cog only (utils NOT reloaded)
  stop                        - Gracefully shutdown the bot
  stop <module>               - Unload a specific cog
  load <module>               - Load a specific cog (must be enabled)
  disable <module>            - Unload and rename file to .py.disabled
  enable <module>             - Rename .py.disabled back to .py (does NOT load)
  sync                        - Manually sync slash commands
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
        print("Bot crashed:", e)
    finally:
        print("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown by user")