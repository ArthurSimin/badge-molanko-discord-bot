import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.gif_spritesheet import process_gif_to_spritesheet
from utils.i18n import t


class GIFToSpritesheet(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="gif_to_spritesheet",
        description=locale_str(
            "Convert an animated GIF into a spritesheet PNG",
            i18n_key="gif_to_spritesheet.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        image=locale_str(
            "The animated GIF image",
            i18n_key="gif_to_spritesheet.param.image",
        ),
        cols=locale_str(
            "Frames per row (0 = auto, default 0)",
            i18n_key="gif_to_spritesheet.param.cols",
        ),
        max_width=locale_str(
            "Max width in px (optional; used when cols=0)",
            i18n_key="gif_to_spritesheet.param.max_width",
        ),
        scale=locale_str(
            "Upscale factor 1-8 (default 1)",
            i18n_key="gif_to_spritesheet.param.scale",
        ),
    )
    async def gif_to_spritesheet(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        cols: int = 0,
        max_width: Optional[int] = None,
        scale: int = 1,
    ):
        await interaction.response.defer(thinking=True)
        locale = str(interaction.locale) if interaction.locale else None

        if scale < 1 or scale > 8:
            await interaction.followup.send(
                t("gif_to_spritesheet.error.scale_range", locale=locale)
            )
            return
        if cols < 0:
            await interaction.followup.send(
                t("gif_to_spritesheet.error.cols_negative", locale=locale)
            )
            return
        if max_width is not None and max_width < 1:
            await interaction.followup.send(
                t("gif_to_spritesheet.error.max_width_min", locale=locale)
            )
            return
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.followup.send(
                t("gif_to_spritesheet.error.invalid_image", locale=locale)
            )
            return

        try:
            img_data = await image.read()
            output, info = await asyncio.to_thread(
                process_gif_to_spritesheet,
                img_data,
                cols,
                max_width,
                scale,
            )
        except ValueError as exc:
            await interaction.followup.send(str(exc))
            return
        except Exception as exc:
            await interaction.followup.send(
                t("gif_to_spritesheet.error.generic", locale=locale, error=exc)
            )
            return

        total_frames, actual_cols, rows, frame_w, frame_h, sheet_w, sheet_h = info
        file = discord.File(output, filename="spritesheet.png")
        await interaction.followup.send(
            content=t(
                "gif_to_spritesheet.success",
                locale=locale,
                total_frames=total_frames,
                actual_cols=actual_cols,
                rows=rows,
                frame_w=frame_w,
                frame_h=frame_h,
                sheet_w=sheet_w,
                sheet_h=sheet_h,
                scale=scale,
            ),
            file=file,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(GIFToSpritesheet(bot))
