import discord
from discord import app_commands
from discord.ext import commands


class WhoAmI(commands.Cog):
    @app_commands.command(name="whoami", description="Show your Discord information")
    async def whoami(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        user = interaction.user

        await interaction.followup.send(
            f"{user.display_name} `{user.id}`"
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(WhoAmI(bot))