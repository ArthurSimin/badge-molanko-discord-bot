import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import sys
import datetime
import logging
import traceback
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

logging.basicConfig(level=logging.INFO)

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
# Bot Class (包含所有事件处理)
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

    # ============================================
    # 事件：普通前缀命令记录
    # ============================================
    async def on_command(self, ctx):
        log_message(
            f"Command invoked by {ctx.author} (ID: {ctx.author.id}) "
            f"with command '{ctx.command.qualified_name}'"
        )

    # ============================================
    # 事件：所有交互（包括斜线命令）记录
    # ============================================
    async def on_interaction(self, interaction):
        if interaction.type == discord.InteractionType.application_command:
            data = interaction.data
            cmd_type = data.get('type')
            cmd_name = data.get('name')

            if cmd_type == 1:
                cmd_label = "Slash command"
            elif cmd_type == 2:
                cmd_label = "User context menu command"
            elif cmd_type == 3:
                cmd_label = "Message context menu command"
            else:
                cmd_label = "Unknown application command"

            log_message(
                f"{cmd_label} invoked by {interaction.user} (ID: {interaction.user.id}) "
                f"with command '{cmd_name}'"
            )

    # ============================================
    # 事件：全局错误兜底
    # ============================================
    async def on_error(self, event, *args, **kwargs):
        print(f"Unhandled error in {event}:")
        traceback.print_exc()

    # ============================================
    # 【关键修复】斜线命令执行错误捕获
    # 解决“命令只记录但不触发”的问题
    # ============================================
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """全局捕获所有斜线命令 / 上下文菜单命令的执行错误"""
        # 获取命令名称（兼容嵌套）
        cmd_name = getattr(interaction.command, 'name', 'unknown')
        
        log_message(f"ERROR in command '{cmd_name}' invoked by {interaction.user}: {error}")
        
        # 打印完整堆栈，方便调试
        traceback.print_exception(type(error), error, error.__traceback__)

        # 如果尚未响应，给用户一个友好的提示（避免交互超时）
        if not interaction.response.is_done():
            try:
                await interaction.response.send_message(
                    f"❌ 命令执行出错，请查看控制台日志。\n错误类型：{type(error).__name__}",
                    ephemeral=True
                )
            except Exception:
                pass  # 发送失败就不处理了

# ======================
# 重试启动主函数
# ======================

async def main():
    max_retries = 5
    retry_delay = 5  # 初始等待秒数

    for attempt in range(1, max_retries + 1):
        # 每次重试都创建一个全新的 Bot 实例，避免状态残留
        bot = MyBot()

        try:
            async with bot:
                await bot.start(TOKEN)
            # 如果启动成功，bot.start() 会阻塞直到机器人关闭，此处 break 退出重试循环
            break

        except discord.LoginFailure:
            print("Invalid TOKEN, please check discord_bot.env")
            break  # Token 错误无需重试

        except Exception as e:
            print(f"Connection attempt {attempt}/{max_retries} failed: {e}")

            if attempt == max_retries:
                print("Max retries reached. Exiting.")
                break

            print(f"Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)
            retry_delay *= 2  # 指数退避

    print("Bot stopped")

# ======================
# 程序入口
# ======================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown by user")