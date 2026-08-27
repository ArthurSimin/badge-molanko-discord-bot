import asyncio
import json
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import locale_for, t


class QuoteProcessingError(Exception):
    pass


async def make_quote_nodejs(options: dict) -> bytes:
    script_path = Path(__file__).parent.parent / "scripts" / "make_quote.js"
    if not script_path.exists():
        raise FileNotFoundError(f"Node.js script not found at {script_path}")

    options_json = json.dumps(options, ensure_ascii=False)

    proc = await asyncio.create_subprocess_exec(
        "node",
        str(script_path),
        options_json,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_msg = stderr.decode().strip() or "Unknown Node.js error"
        raise QuoteProcessingError(f"Node.js processing failed: {error_msg}")

    if not stdout:
        raise QuoteProcessingError("Node.js returned empty image data")

    return stdout


def _message_text(message: discord.Message) -> str:
    text = (message.content or "").strip()
    if text:
        return text
    if message.embeds:
        emb = message.embeds[0]
        parts = []
        if emb.title:
            parts.append(emb.title)
        if emb.description:
            parts.append(emb.description)
        if parts:
            return "\n".join(parts)
    if message.stickers:
        return message.stickers[0].name
    if message.attachments:
        return "[attachment]"
    return ""


class QuoteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name=locale_str(
                "Make it a Quote",
                i18n_key="quote.context_name",
            ),
            callback=self.quote_context,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def _generate_and_send(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
        theme: str = "dark",
    ) -> None:
        locale = locale_for(interaction)

        text = _message_text(message)
        if not text:
            await interaction.followup.send(
                t("quote.error.no_content", locale=locale),
                ephemeral=True,
            )
            return

        author = message.author
        display_name = author.display_name
        username = getattr(author, "name", None) or str(author)
        avatar_url = author.display_avatar.url

        options = {
            "text": text,
            "avatar": avatar_url,
            "username": username,
            "displayName": display_name,
            "theme": theme or "dark",
        }

        try:
            png_bytes = await make_quote_nodejs(options)
        except QuoteProcessingError as e:
            await interaction.followup.send(
                t("quote.error.processing", locale=locale, error=e),
                ephemeral=True,
            )
            return
        except FileNotFoundError:
            await interaction.followup.send(
                t("quote.error.script_not_found", locale=locale),
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(
                t("quote.error.unexpected", locale=locale, error=e),
                ephemeral=True,
            )
            return

        file = discord.File(BytesIO(png_bytes), filename="quote.png")
        await interaction.followup.send(
            content=t(
                "quote.success",
                locale=locale,
                author=display_name,
            ),
            file=file,
        )

    @app_commands.command(
        name="quote",
        description=locale_str(
            "Turn a message into a quote image",
            i18n_key="quote.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        message_id=locale_str(
            "Message ID to quote (optional if you reply to a message)",
            i18n_key="quote.param.message_id",
        ),
        theme=locale_str(
            "Theme: dark / light / color / portrait / portrait-light",
            i18n_key="quote.param.theme",
        ),
    )
    @app_commands.choices(
        theme=[
            app_commands.Choice(
                name=locale_str("dark", i18n_key="quote.choice.dark"),
                value="dark",
            ),
            app_commands.Choice(
                name=locale_str("light", i18n_key="quote.choice.light"),
                value="light",
            ),
            app_commands.Choice(
                name=locale_str("color", i18n_key="quote.choice.color"),
                value="color",
            ),
            app_commands.Choice(
                name=locale_str("portrait", i18n_key="quote.choice.portrait"),
                value="portrait",
            ),
            app_commands.Choice(
                name=locale_str(
                    "portrait-light",
                    i18n_key="quote.choice.portrait_light",
                ),
                value="portrait-light",
            ),
        ]
    )
    async def quote(
        self,
        interaction: discord.Interaction,
        message_id: Optional[str] = None,
        theme: str = "dark",
    ):
        await interaction.response.defer(thinking=True)
        locale = locale_for(interaction)

        target: Optional[discord.Message] = None

        if interaction.message and interaction.message.reference:
            ref_id = interaction.message.reference.message_id
            if ref_id is not None:
                try:
                    target = await interaction.channel.fetch_message(ref_id)
                except Exception:
                    pass

        if target is None and message_id:
            try:
                target = await interaction.channel.fetch_message(int(message_id))
            except (ValueError, discord.NotFound, discord.HTTPException, discord.Forbidden):
                await interaction.followup.send(
                    t("quote.error.message_not_found", locale=locale),
                    ephemeral=True,
                )
                return

        if target is None:
            await interaction.followup.send(
                t("quote.error.need_message", locale=locale),
                ephemeral=True,
            )
            return

        await self._generate_and_send(interaction, target, theme=theme)

    async def quote_context(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ):
        await interaction.response.defer(thinking=True)
        await self._generate_and_send(interaction, message, theme="dark")


async def setup(bot: commands.Bot):
    await bot.add_cog(QuoteCog(bot))
