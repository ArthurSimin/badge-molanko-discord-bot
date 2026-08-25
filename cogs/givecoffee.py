import asyncio

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import locale_for, t


class givecoffee(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="givecoffee",
        description=locale_str(
            "Give coffee",
            i18n_key="givecoffee.command_description",
        ),
    )
    @app_commands.describe(
        process=locale_str(
            "Show the coffee-making process",
            i18n_key="givecoffee.process_description",
        ),
    )
    @app_commands.allowed_contexts(
        guilds=True,
        dms=True,
        private_channels=True,
    )
    async def give_coffee(
        self,
        interaction: discord.Interaction,
        process: bool = True,
    ):
        locale = locale_for(interaction)

        if not process:
            await interaction.response.send_message(
                t("givecoffee.coffee", locale=locale)
            )
            return

        await interaction.response.send_message(
            t("givecoffee.step.grind", locale=locale)
        )

        await asyncio.sleep(12)

        await interaction.edit_original_response(
            content=t("givecoffee.step.heat", locale=locale)
        )

        await asyncio.sleep(10)

        await interaction.edit_original_response(
            content=t("givecoffee.step.brew", locale=locale)
        )

        await asyncio.sleep(8)

        await interaction.edit_original_response(
            content=t("givecoffee.coffee", locale=locale)
        )

        await interaction.followup.send(
            content=t(
                "givecoffee.done",
                locale=locale
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(givecoffee(bot))