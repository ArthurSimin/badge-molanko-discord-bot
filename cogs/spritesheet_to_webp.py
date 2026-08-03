import io
import math
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image


class SpritesheetToWebP(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="spritesheet_to_webp",
        description="Extract frames from a spritesheet and generate an animated WebP"
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        image="The spritesheet image (PNG/GIF/WebP)",
        frame_width="Width of each frame in pixels (default 32)",
        frame_height="Height of each frame in pixels (default 32)",
        cols="Number of columns (frames per row). Auto-calculated if not set",
        rows="Number of rows. Auto-calculated if not set",
        delay="Delay between frames in milliseconds (default 100)",
        start_frame="First frame index (0‑based, default 0)",
        end_frame="Last frame index (inclusive). Omit to use all",
        scale="Upscale factor for exported WebP (keeps pixels sharp, default 2)"
    )
    async def spritesheet_to_webp(
        self,
        interaction: discord.Interaction,
        image: discord.Attachment,
        frame_width: int = 32,
        frame_height: int = 32,
        cols: Optional[int] = None,
        rows: Optional[int] = None,
        delay: int = 100,
        start_frame: int = 0,
        end_frame: Optional[int] = None,
        scale: int = 2
    ):
        await interaction.response.defer(thinking=True)

        # Basic validation
        if frame_width < 1 or frame_height < 1:
            await interaction.followup.send("Frame width and height must be at least 1.")
            return
        if delay < 10:
            await interaction.followup.send("Delay must be at least 10 ms.")
            return
        if start_frame < 0:
            await interaction.followup.send("Start frame cannot be negative.")
            return
        if scale < 1 or scale > 8:
            await interaction.followup.send("Scale must be between 1 and 8.")
            return
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.followup.send("Please upload a valid image file.")
            return

        try:
            # Download image
            img_data = await image.read()
            spritesheet = Image.open(io.BytesIO(img_data))
            # Convert to RGBA to simplify processing (preserve transparency)
            if spritesheet.mode not in ("RGBA", "RGB", "P"):
                spritesheet = spritesheet.convert("RGBA")
            elif spritesheet.mode == "P":
                spritesheet = spritesheet.convert("RGBA")

            sheet_width, sheet_height = spritesheet.size

            # Auto-calculate cols/rows if missing
            if cols is None and rows is None:
                cols = sheet_width // frame_width
                rows = sheet_height // frame_height
                if cols == 0 or rows == 0:
                    await interaction.followup.send(
                        f"Frame size ({frame_width}×{frame_height}) is larger than the image "
                        f"({sheet_width}×{sheet_height}). Please adjust."
                    )
                    return
            elif cols is None:
                max_frames = (sheet_width // frame_width) * (sheet_height // frame_height)
                total_frames = max_frames
                cols = total_frames // rows
                if cols == 0:
                    await interaction.followup.send(
                        f"With {rows} rows, the calculated columns would be 0. "
                        "Please adjust rows or frame size."
                    )
                    return
            elif rows is None:
                total_frames = (sheet_width // frame_width) * (sheet_height // frame_height)
                rows = total_frames // cols
                if rows == 0:
                    await interaction.followup.send(
                        f"With {cols} columns, the calculated rows would be 0. "
                        "Please adjust cols or frame size."
                    )
                    return

            # Validate cols/rows fit the image
            max_cols = sheet_width // frame_width
            max_rows = sheet_height // frame_height
            if cols > max_cols:
                await interaction.followup.send(
                    f"Columns ({cols}) exceed the maximum possible ({max_cols}) given the frame width."
                )
                return
            if rows > max_rows:
                await interaction.followup.send(
                    f"Rows ({rows}) exceed the maximum possible ({max_rows}) given the frame height."
                )
                return

            total_frames = cols * rows
            if start_frame >= total_frames:
                await interaction.followup.send(
                    f"Start frame {start_frame} is out of range (0–{total_frames-1})."
                )
                return

            if end_frame is None:
                end_frame = total_frames - 1
            else:
                if end_frame < start_frame:
                    await interaction.followup.send("End frame must be >= start frame.")
                    return
                if end_frame >= total_frames:
                    await interaction.followup.send(
                        f"End frame {end_frame} exceeds maximum {total_frames-1}."
                    )
                    return

            # Extract frames
            frames = []
            for idx in range(start_frame, end_frame + 1):
                col = idx % cols
                row = idx // cols
                left = col * frame_width
                top = row * frame_height
                frame = spritesheet.crop((left, top, left + frame_width, top + frame_height))
                frames.append(frame)

            if not frames:
                await interaction.followup.send("No frames extracted. Check your parameters.")
                return

            # Scale frames if needed
            if scale != 1:
                scaled_frames = []
                new_size = (frame_width * scale, frame_height * scale)
                for f in frames:
                    scaled = f.resize(new_size, Image.NEAREST)
                    scaled_frames.append(scaled)
                frames = scaled_frames
                frame_width, frame_height = new_size

            # Generate animated WebP in memory
            output = io.BytesIO()
            # Save as animated WebP
            frames[0].save(
                output,
                format="WEBP",
                save_all=True,
                append_images=frames[1:],
                loop=0,
                duration=delay,
                lossless=True,        # can be set to True for lossless; False gives smaller size
                quality=100,            # adjust as needed; 80 is a good balance
                method=4               # compression method (0-6, 6 is slowest but best compression)
            )
            output.seek(0)

            # Send result
            file = discord.File(output, filename="animation.webp")
            await interaction.followup.send(
                content=(
                    f"✅ Animated WebP generated:\n"
                    f"• Frames: {len(frames)}\n"
                    f"• Resolution: {frame_width}×{frame_height}\n"
                    f"• Delay: {delay} ms\n"
                    f"• Scale: {scale}×"
                ),
                file=file
            )

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(SpritesheetToWebP(bot))