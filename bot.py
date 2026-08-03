import discord
from discord.ext import commands
import os
import asyncio
import sys
import datetime          # 新增
from dotenv import load_dotenv

# 导入命令处理器
from terminal_commands import TerminalCommandHandler

# ======================
# Logging function
# ======================

def log_message(msg: str):
    """Print a timestamped log message to console."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

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
        self.cogs_dir = COGS_DIR
        self.utils_dir = UTILS_DIR
        self._terminal_task = None
        self._shutdown = False

        # 初始化命令处理器
        self.cmd_handler = TerminalCommandHandler(self)

    async def setup_hook(self):
        print("Loading cogs...")

        if os.path.exists(self.cogs_dir):
            for filename in os.listdir(self.cogs_dir):
                if filename.endswith(".py") and not filename.startswith("_"):
                    extension = f"cogs.{filename[:-3]}"
                    try:
                        await self.load_extension(extension)
                        print(f"Loaded {extension}")
                    except Exception as e:
                        print(f"Failed loading {extension}: {e}")
        else:
            print("cogs folder not found")

        # 同步斜线命令
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

        # 启动终端命令循环
        self._terminal_task = asyncio.create_task(self.terminal_loop())

    async def terminal_loop(self):
        """从 stdin 读取命令并分发到处理器"""
        loop = asyncio.get_event_loop()
        while not self._shutdown:
            try:
                sys.stdout.write("> ")
                sys.stdout.flush()

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

                await self.cmd_handler.dispatch(cmd, arg)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in terminal loop: {e}")

# ======================
# Instantiate bot
# ======================

bot = MyBot()

# ======================
# Event loggers
# ======================

@bot.event
async def on_command(ctx):
    """记录前缀命令调用"""
    log_message(
        f"Command invoked by {ctx.author} (ID: {ctx.author.id}) "
        f"with command '{ctx.command.qualified_name}'"
    )

@bot.event
async def on_interaction(interaction):
    """记录斜线命令（以及可能的组件交互，这里只记录应用命令）"""
    if interaction.type == discord.InteractionType.application_command:
        log_message(
            f"Slash command invoked by {interaction.user} (ID: {interaction.user.id}) "
            f"with command '{interaction.data['name']}'"
        )

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