import io
import math
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageSequence


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
        scale: int = 1
    ):
        await interaction.response.defer(thinking=True)

        # Validate inputs
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
            # Download image
            img_data = await image.read()
            with Image.open(io.BytesIO(img_data)) as gif:
                if not getattr(gif, "is_animated", False):
                    await interaction.followup.send(
                        "This image is not animated. Please provide a GIF or other animated format."
                    )
                    return

                # Extract frames (convert to RGBA)
                frames = []
                for frame in ImageSequence.Iterator(gif):
                    frame_rgba = frame.convert("RGBA")
                    frames.append(frame_rgba)

                if not frames:
                    await interaction.followup.send("No frames could be extracted.")
                    return

                # Ensure same size
                first_w, first_h = frames[0].size
                for i, f in enumerate(frames):
                    if f.size != (first_w, first_h):
                        f = f.resize((first_w, first_h), Image.NEAREST)
                        frames[i] = f

                total_frames = len(frames)

                # Determine number of columns
                if cols > 0:
                    # User specified columns
                    pass
                elif max_width is not None:
                    # Calculate cols based on max_width
                    # Each frame's scaled width
                    frame_scaled_w = first_w * scale
                    cols = max(1, max_width // frame_scaled_w)
                    # But we shouldn't have more cols than frames
                    cols = min(cols, total_frames)
                else:
                    # Auto calculate: try to make the spritesheet roughly square
                    # First, compute area: total frames * frame area
                    # We want rows ≈ cols, so cols ≈ sqrt(total_frames)
                    # But also ensure cols * frame_width is not too excessive
                    # Let's aim for a ratio between 0.5 and 2 for width/height
                    # Start with sqrt(total_frames)
                    ideal_cols = math.ceil(math.sqrt(total_frames))
                    # But also ensure total width is not too huge (cap at 8 times frame width)
                    max_reasonable_cols = max(1, min(8, total_frames))
                    # Use the smaller of the two
                    cols = min(ideal_cols, max_reasonable_cols)
                    # Ensure at least 1
                    cols = max(1, cols)

                rows = math.ceil(total_frames / cols)

                # Apply scaling to frames
                if scale != 1:
                    scaled_w = first_w * scale
                    scaled_h = first_h * scale
                    scaled_frames = []
                    for f in frames:
                        scaled = f.resize((scaled_w, scaled_h), Image.NEAREST)
                        scaled_frames.append(scaled)
                    frames = scaled_frames
                    frame_w, frame_h = scaled_w, scaled_h
                else:
                    frame_w, frame_h = first_w, first_h

                # Create spritesheet
                spritesheet_w = cols * frame_w
                spritesheet_h = rows * frame_h
                spritesheet = Image.new("RGBA", (spritesheet_w, spritesheet_h), (0, 0, 0, 0))

                for idx, frame in enumerate(frames):
                    x = (idx % cols) * frame_w
                    y = (idx // cols) * frame_h
                    spritesheet.paste(frame, (x, y), frame)

                # Save
                output = io.BytesIO()
                spritesheet.save(output, format="PNG")
                output.seek(0)

                file = discord.File(output, filename="spritesheet.png")
                await interaction.followup.send(
                    content=(
                        f"✅ Spritesheet generated:\n"
                        f"• Frames: {total_frames}\n"
                        f"• Grid: {cols}×{rows}\n"
                        f"• Frame size: {frame_w}×{frame_h}\n"
                        f"• Total size: {spritesheet_w}×{spritesheet_h}\n"
                        f"• Scale: {scale}×"
                    ),
                    file=file
                )

        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(GIFToSpritesheet(bot))