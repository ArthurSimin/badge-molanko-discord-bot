import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.gif_spritesheet import process_gif_to_spritesheet


class GIFToSpritesheet(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="gif_to_spritesheet",
        description="Convert an animated GIF into a spritesheet (PNG) with all frames arranged in a grid."
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        image="The animated GIF image",
        cols="Number of frames per row (0 = auto, default 0)",
        max_width="Maximum width in pixels (optional, auto calculates columns if cols=0)",
        scale="Upscale factor for the spritesheet (1-8, keeps pixels sharp, default 1)"
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

        if scale < 1 or scale > 8:
            await interaction.followup.send("Scale must be between 1 and 8.")
            return
        if cols < 0:
            await interaction.followup.send("Columns cannot be negative.")
            return
        if max_width is not None and max_width < 1:
            await interaction.followup.send("max_width must be at least 1 pixel.")
            return
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.followup.send("Please upload a valid image file.")
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
            await interaction.followup.send(f"An error occurred: {exc}")
            return

        total_frames, actual_cols, rows, frame_w, frame_h, sheet_w, sheet_h = info
        file = discord.File(output, filename="spritesheet.png")
        await interaction.followup.send(
            content=(
                "✅ Spritesheet generated:\n"
                f"• Frames: {total_frames}\n"
                f"• Grid: {actual_cols}×{rows}\n"
                f"• Frame size: {frame_w}×{frame_h}\n"
                f"• Total size: {sheet_w}×{sheet_h}\n"
                f"• Scale: {scale}×"
            ),
            file=file,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(GIFToSpritesheet(bot))
