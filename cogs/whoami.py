import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands
from utils.i18n import t

class WhoAmI(commands.Cog):
    @app_commands.command(name="whoami", description=locale_str("Who am I?", i18n_key="whoami.command_description"))
    async def whoami(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        user = interaction.user

        await interaction.followup.send(
            f"{user.display_name} `{user.id}`"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(WhoAmI(bot))