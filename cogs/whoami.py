# whoami.py
import discord
from discord import app_commands
from discord.ext import commands

class WhoAmI(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="whoami", description="Display information about yourself")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def whoami(self, interaction: discord.Interaction):
        user = interaction.user

        # 构建一个美观的 Embed
        embed = discord.Embed(
            title="👤 Your Information",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="Username", value=f"{user.name}#{user.discriminator}" if user.discriminator != "0" else user.name, inline=True)
        embed.add_field(name="Global Name", value=user.global_name or "Not set", inline=True)
        embed.add_field(name="User ID", value=f"`{user.id}`", inline=False)
        embed.add_field(name="Account Created", value=f"<t:{int(user.created_at.timestamp())}:F>", inline=True)
        embed.add_field(name="Is Bot?", value="🤖 Yes" if user.bot else "👤 No", inline=True)
        embed.set_footer(text=f"Requested by {user.display_name}", icon_url=user.display_avatar.url)

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(WhoAmI(bot))