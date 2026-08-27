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
from discord.ui import View

from utils.i18n import locale_for, t


class QuoteProcessingError(Exception):
    pass


# Discord allows at most 25 choices. Stacks always end with CJK-capable fallbacks.
QUOTE_FONTS: dict[str, str] = {
    "sc": "Noto Sans SC, Noto Sans TC, Noto Sans JP, sans-serif",
    "tc": "Noto Sans TC, Noto Sans SC, Noto Sans JP, sans-serif",
    "serif_sc": "Noto Serif SC, Noto Sans SC, sans-serif",
    "serif_tc": "Noto Serif TC, Noto Sans TC, sans-serif",
    "rounded": "M PLUS Rounded 1c, Noto Sans SC, Noto Sans JP, sans-serif",
    "gothic": "Dela Gothic One, Noto Sans SC, Noto Sans JP, sans-serif",
    "pixel": "DotGothic16, Noto Sans SC, sans-serif",
    "mincho": "Zen Old Mincho, Noto Serif SC, Noto Sans SC, sans-serif",
    "pop": "Hachi Maru Pop, Noto Sans SC, sans-serif",
    "rock": "RocknRoll One, Noto Sans SC, sans-serif",
    "mashan": "Ma Shan Zheng, Noto Sans SC, sans-serif",
    "xiaowei": "ZCOOL XiaoWei, Noto Sans SC, sans-serif",
    "huangyou": "ZCOOL QingKe HuangYou, Noto Sans SC, sans-serif",
    "exo": "Exo 2, Noto Sans SC, sans-serif",
    "script": "Dancing Script, Noto Sans SC, sans-serif",
}

DEFAULT_FONT_KEY = "sc"


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


def _font_stack(font_key: Optional[str]) -> str:
    if font_key and font_key in QUOTE_FONTS:
        return QUOTE_FONTS[font_key]
    return QUOTE_FONTS[DEFAULT_FONT_KEY]


class QuoteFontView(View):
    """Ephemeral font picker for message context menu."""

    def __init__(
        self,
        cog: "QuoteCog",
        message: discord.Message,
        locale: str | None,
    ):
        super().__init__(timeout=120)
        self.cog = cog
        self.message = message
        self.locale = locale
        self.font_key = DEFAULT_FONT_KEY

        options = [
            discord.SelectOption(
                label=t(f"quote.font.{key}", locale=locale),
                value=key,
                description=QUOTE_FONTS[key].split(",")[0].strip()[:100],
                default=(key == DEFAULT_FONT_KEY),
            )
            for key in QUOTE_FONTS
        ]
        select = discord.ui.Select(
            placeholder=t("quote.view.font_placeholder", locale=locale),
            options=options[:25],
            min_values=1,
            max_values=1,
        )
        select.callback = self.on_select
        self.add_item(select)

        button = discord.ui.Button(
            label=t("quote.view.generate_button", locale=locale),
            style=discord.ButtonStyle.primary,
        )
        button.callback = self.on_generate
        self.add_item(button)

    async def on_select(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values") if interaction.data else None
        if values:
            self.font_key = values[0]
        await interaction.response.defer()

    async def on_generate(self, interaction: discord.Interaction) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Select) and child.values:
                self.font_key = child.values[0]
                break

        await interaction.response.defer(thinking=True, ephemeral=False)
        await self.cog._generate_and_send(
            interaction,
            self.message,
            theme="dark",
            font_key=self.font_key,
        )
        self.stop()


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
        font_key: Optional[str] = None,
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
            "font": _font_stack(font_key),
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
        font=locale_str(
            "Font for the quote text",
            i18n_key="quote.param.font",
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
        ],
        font=[
            app_commands.Choice(
                name=locale_str("Noto Sans SC", i18n_key="quote.font.sc"),
                value="sc",
            ),
            app_commands.Choice(
                name=locale_str("Noto Sans TC", i18n_key="quote.font.tc"),
                value="tc",
            ),
            app_commands.Choice(
                name=locale_str("Noto Serif SC", i18n_key="quote.font.serif_sc"),
                value="serif_sc",
            ),
            app_commands.Choice(
                name=locale_str("Noto Serif TC", i18n_key="quote.font.serif_tc"),
                value="serif_tc",
            ),
            app_commands.Choice(
                name=locale_str("M PLUS Rounded", i18n_key="quote.font.rounded"),
                value="rounded",
            ),
            app_commands.Choice(
                name=locale_str("Dela Gothic One", i18n_key="quote.font.gothic"),
                value="gothic",
            ),
            app_commands.Choice(
                name=locale_str("DotGothic16", i18n_key="quote.font.pixel"),
                value="pixel",
            ),
            app_commands.Choice(
                name=locale_str("Zen Old Mincho", i18n_key="quote.font.mincho"),
                value="mincho",
            ),
            app_commands.Choice(
                name=locale_str("Hachi Maru Pop", i18n_key="quote.font.pop"),
                value="pop",
            ),
            app_commands.Choice(
                name=locale_str("RocknRoll One", i18n_key="quote.font.rock"),
                value="rock",
            ),
            app_commands.Choice(
                name=locale_str("Ma Shan Zheng", i18n_key="quote.font.mashan"),
                value="mashan",
            ),
            app_commands.Choice(
                name=locale_str("ZCOOL XiaoWei", i18n_key="quote.font.xiaowei"),
                value="xiaowei",
            ),
            app_commands.Choice(
                name=locale_str(
                    "ZCOOL QingKe HuangYou",
                    i18n_key="quote.font.huangyou",
                ),
                value="huangyou",
            ),
            app_commands.Choice(
                name=locale_str("Exo 2", i18n_key="quote.font.exo"),
                value="exo",
            ),
            app_commands.Choice(
                name=locale_str("Dancing Script", i18n_key="quote.font.script"),
                value="script",
            ),
        ],
    )
    async def quote(
        self,
        interaction: discord.Interaction,
        message_id: Optional[str] = None,
        theme: str = "dark",
        font: str = DEFAULT_FONT_KEY,
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

        await self._generate_and_send(
            interaction,
            target,
            theme=theme,
            font_key=font,
        )

    async def quote_context(
        self,
        interaction: discord.Interaction,
        message: discord.Message,
    ):
        locale = locale_for(interaction)
        view = QuoteFontView(self, message, locale)
        await interaction.response.send_message(
            t("quote.context.prompt", locale=locale),
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(QuoteCog(bot))
