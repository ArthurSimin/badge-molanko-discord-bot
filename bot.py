import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
import asyncio

load_dotenv("discord_bot.env")

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise ValueError("TOKEN not found in discord_bot.env")

intents = discord.Intents.default()
# Presence intent is privileged and must be enabled in the Discord Developer Portal.
# Disable it here unless you explicitly enable it there.
intents.presences = False

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    
    # Set online status
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="/time | /version"
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

    # Sync slash commands
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

    print("🤖 Bot is ready and online!")

async def load_extensions():
    """Load all cogs"""
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and not filename.startswith("_"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅ Loaded: {filename}")
            except Exception as e:
                print(f"❌ Failed to load {filename}: {e}")

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped.")