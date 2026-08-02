import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv


# ======================
# 路径设置
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
# 读取 TOKEN
# ======================

load_dotenv(ENV_FILE)

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError(
        "❌ TOKEN not found in discord_bot.env"
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


    async def setup_hook(self):

        print("🔄 Loading cogs...")


        # 加载所有 Cog
        if os.path.exists(COGS_DIR):

            for filename in os.listdir(COGS_DIR):

                if (
                    filename.endswith(".py")
                    and not filename.startswith("_")
                ):

                    extension = (
                        f"cogs.{filename[:-3]}"
                    )

                    try:
                        await self.load_extension(
                            extension
                        )

                        print(
                            f"✅ Loaded {extension}"
                        )

                    except Exception as e:

                        print(
                            f"❌ Failed loading {extension}"
                        )

                        print(e)


        else:

            print(
                "⚠️ cogs folder not found"
            )


        # 同步 Slash Commands

        try:

            synced = await self.tree.sync()

            print(
                f"✅ Synced {len(synced)} slash command(s)"
            )


        except Exception as e:

            print(
                "❌ Slash sync failed:"
            )

            print(e)



bot = MyBot()



# ======================
# Bot Ready
# ======================

@bot.event
async def on_ready():

    print(
        "========================"
    )

    print(
        f"🤖 Logged in as: {bot.user}"
    )

    print(
        f"🆔 ID: {bot.user.id}"
    )

    print(
        f"🌐 Servers: {len(bot.guilds)}"
    )


    # 设置状态

    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="/time | /version"
    )


    await bot.change_presence(
        status=discord.Status.online,
        activity=activity
    )


    print(
        "✅ Bot is ONLINE!"
    )

    print(
        "========================"
    )



# ======================
# 错误处理
# ======================

@bot.event
async def on_error(event, *args, **kwargs):

    print(
        f"❌ Error in {event}"
    )



# ======================
# 启动
# ======================

async def main():

    try:

        async with bot:

            await bot.start(TOKEN)


    except discord.LoginFailure:

        print(
            "❌ TOKEN错误，请检查 discord_bot.env"
        )


    except Exception as e:

        print(
            "❌ Bot crashed:"
        )

        print(e)


    finally:

        print(
            "🛑 Bot stopped"
        )



if __name__ == "__main__":

    try:

        asyncio.run(main())


    except KeyboardInterrupt:

        print(
            "\n🛑 Shutdown by user"
        )