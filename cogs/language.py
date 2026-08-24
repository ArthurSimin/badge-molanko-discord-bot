import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import locale_display_name, locale_for, list_supported_locales, t
from utils.user_locale import get_user_locale, set_user_locale


def _language_choices() -> list[app_commands.Choice[str]]:
    choices = [
        app_commands.Choice(
            name=locale_str("Auto", i18n_key="language.choice.auto"),
            value="auto",
        )
    ]
    for code in list_supported_locales():
        label = {
            "en": "English",
            "zh-CN": "Simplified Chinese",
        }.get(code, code)
        choices.append(
            app_commands.Choice(
                name=locale_str(label, i18n_key=f"language.locale.{code}"),
                value=code,
            )
        )
    return choices


class Language(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="language",
        description=locale_str(
            "Set the language for bot replies to you",
            i18n_key="language.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        language=locale_str(
            "Language for replies (Auto follows Discord client)",
            i18n_key="language.param.language",
        ),
    )
    @app_commands.choices(language=_language_choices())
    async def language(
        self,
        interaction: discord.Interaction,
        language: app_commands.Choice[str] | None = None,
    ):
        if language is not None:
            set_user_locale(interaction.user.id, language.value)
            reply_locale = None if language.value == "auto" else language.value
            if reply_locale is None:
                reply_locale = locale_for(interaction)
            display = locale_display_name(language.value, for_locale=reply_locale)
            await interaction.response.send_message(
                t(
                    "language.set",
                    locale=reply_locale,
                    language=display,
                ),
                ephemeral=True,
            )
            return

        locale = locale_for(interaction)
        pref = get_user_locale(interaction.user.id)
        current = locale_display_name(pref, for_locale=locale)
        supported = ", ".join(
            locale_display_name(c, for_locale=locale)
            for c in ["auto", *list_supported_locales()]
        )
        await interaction.response.send_message(
            t(
                "language.status",
                locale=locale,
                current=current,
                supported=supported,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Language(bot))
