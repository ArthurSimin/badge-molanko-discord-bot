import io
import asyncio
import math
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image


def log_message(msg: str):
    """Print a timestamped log message to console."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [spritesheet_animation] {msg}")


def unify_palette(frames):
    """
    Convert all frames to 'P' mode using a single global palette.
    This prevents colour shifting in GIF animations.
    """
    if not frames:
        return frames

    log_message("Unifying palette for GIF...")
    # Convert all frames to RGB (discard alpha) for palette unification
    rgb_frames = [f.convert("RGB") for f in frames]

    # Quantize the first frame to generate a global palette (256 colours)
    palette_img = rgb_frames[0].quantize(colors=256, method=Image.MEDIANCUT, dither=Image.NONE)

    # Convert all frames to 'P' using the same palette
    unified = []
    for i, img in enumerate(rgb_frames):
        if i == 0:
            unified.append(palette_img)
        else:
            q = img.quantize(palette=palette_img, dither=Image.NONE)
            unified.append(q)

    log_message(f"Palette unification complete, {len(unified)} frames processed.")
    return unified


class SpritesheetToAnimation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="spritesheet_to_animation",
        description="Extract frames from a spritesheet and output as GIF or animated WebP"
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
        scale="Upscale factor for exported animation (keeps pixels sharp, default 2)",
        format="Output format: 'gif' or 'webp' (default gif)",
        lossless="For WebP only: enable lossless compression (default False)",
        quality="For WebP only: quality 1-100 (default 80)"
    )
    @app_commands.choices(format=[
        app_commands.Choice(name="GIF", value="gif"),
        app_commands.Choice(name="WebP", value="webp")
    ])
    async def spritesheet_to_animation(
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
        scale: int = 2,
        format: str = "gif",
        lossless: bool = False,
        quality: int = 80
    ):
        await interaction.response.defer(thinking=True)
        log_message(f"Command invoked by {interaction.user} (ID: {interaction.user.id})")

        # -------- Parameter validation --------
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
        if format not in ("gif", "webp"):
            await interaction.followup.send("Format must be either 'gif' or 'webp'.")
            return
        if quality < 1 or quality > 100:
            await interaction.followup.send("Quality must be between 1 and 100.")
            return
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.followup.send("Please upload a valid image file.")
            return

        try:
            # Read image data asynchronously
            log_message("Downloading image...")
            img_data = await image.read()
            log_message(f"Image downloaded, size: {len(img_data)} bytes")
        except Exception as e:
            log_message(f"Failed to read image: {e}")
            await interaction.followup.send(f"Failed to read image: {e}")
            return

        # -------- Define the heavy processing function --------
        def process_images(data, fw, fh, c, r, dly, start, end, sc, fmt, loss, qual):
            try:
                log_message("Starting image processing in thread...")
                spritesheet = Image.open(io.BytesIO(data))
                log_message(f"Image opened: {spritesheet.size}, mode: {spritesheet.mode}")
                # Normalise to RGBA for consistent cropping
                if spritesheet.mode not in ("RGBA", "RGB", "P"):
                    spritesheet = spritesheet.convert("RGBA")
                    log_message("Converted image to RGBA")
                elif spritesheet.mode == "P":
                    spritesheet = spritesheet.convert("RGBA")
                    log_message("Converted palette image to RGBA")

                sheet_w, sheet_h = spritesheet.size

                # -------- Calculate columns/rows --------
                log_message("Calculating columns/rows...")
                if c is None and r is None:
                    c = sheet_w // fw
                    r = sheet_h // fh
                    if c == 0 or r == 0:
                        raise ValueError(f"Frame size ({fw}×{fh}) larger than image ({sheet_w}×{sheet_h}).")
                    log_message(f"Auto-calculated: cols={c}, rows={r}")
                elif c is None:
                    max_frames = (sheet_w // fw) * (sheet_h // fh)
                    c = max_frames // r
                    if c == 0:
                        raise ValueError(f"With {r} rows, columns would be 0. Adjust rows or frame size.")
                    log_message(f"Calculated cols from rows: cols={c}, rows={r}")
                elif r is None:
                    total_frames = (sheet_w // fw) * (sheet_h // fh)
                    r = total_frames // c
                    if r == 0:
                        raise ValueError(f"With {c} columns, rows would be 0. Adjust cols or frame size.")
                    log_message(f"Calculated rows from cols: cols={c}, rows={r}")

                max_c = sheet_w // fw
                max_r = sheet_h // fh
                if c > max_c:
                    raise ValueError(f"Columns ({c}) exceed maximum {max_c}.")
                if r > max_r:
                    raise ValueError(f"Rows ({r}) exceed maximum {max_r}.")

                total = c * r
                log_message(f"Total frames in spritesheet: {total}")
                if start >= total:
                    raise ValueError(f"Start frame {start} out of range (0–{total-1}).")
                if end is None:
                    end = total - 1
                    log_message(f"End frame not set, using last frame: {end}")
                else:
                    if end < start:
                        raise ValueError("End frame must be >= start frame.")
                    if end >= total:
                        raise ValueError(f"End frame {end} exceeds maximum {total-1}.")
                    log_message(f"End frame set to: {end}")

                # -------- Extract frames --------
                frame_count = end - start + 1
                log_message(f"Extracting {frame_count} frames from index {start} to {end}...")
                frame_list = []
                for idx in range(start, end + 1):
                    col = idx % c
                    row = idx // c
                    left = col * fw
                    top = row * fh
                    frame = spritesheet.crop((left, top, left + fw, top + fh))
                    frame_list.append(frame)
                    # Log progress every 10 frames
                    if (idx - start + 1) % 10 == 0 or (idx - start + 1) == frame_count:
                        log_message(f"Extracted {idx - start + 1}/{frame_count} frames")

                if not frame_list:
                    raise ValueError("No frames extracted. Check parameters.")
                log_message(f"Extraction complete, {len(frame_list)} frames captured.")

                # -------- Scale frames --------
                if sc != 1:
                    log_message(f"Scaling frames by {sc}x...")
                    new_size = (fw * sc, fh * sc)
                    scaled = []
                    for i, f in enumerate(frame_list):
                        scaled.append(f.resize(new_size, Image.NEAREST))
                        if (i + 1) % 10 == 0 or (i + 1) == len(frame_list):
                            log_message(f"Scaled {i+1}/{len(frame_list)} frames")
                    frame_list = scaled
                    fw, fh = new_size
                    log_message(f"Scaling complete, new size: {fw}×{fh}")

                # -------- Format specific processing --------
                out_bytes = io.BytesIO()
                if fmt == "gif":
                    log_message("Preparing GIF output with unified palette...")
                    # For GIF, we want a unified global palette to avoid colour shifting
                    rgb_frames = [f.convert("RGB") for f in frame_list]
                    unified = unify_palette(rgb_frames)  # returns P mode frames with common palette

                    log_message("Saving GIF...")
                    unified[0].save(
                        out_bytes,
                        format="GIF",
                        save_all=True,
                        append_images=unified[1:],
                        loop=0,
                        duration=dly,
                        optimize=False,
                        disposal=2,
                        palette=None   # frames already have consistent palette
                    )
                    filename = "animation.gif"
                else:  # webp
                    log_message("Preparing WebP output...")
                    first = frame_list[0]
                    if first.mode == "RGBA":
                        mode = "RGBA"
                    else:
                        mode = "RGB"
                    webp_frames = [f.convert(mode) for f in frame_list]
                    log_message(f"All frames converted to {mode} for WebP.")

                    log_message(f"Saving animated WebP (lossless={loss}, quality={qual})...")
                    webp_frames[0].save(
                        out_bytes,
                        format="WEBP",
                        save_all=True,
                        append_images=webp_frames[1:],
                        loop=0,
                        duration=dly,
                        lossless=loss,
                        quality=qual,
                        method=4       # fixed compression method (0-6)
                    )
                    filename = "animation.webp"

                out_bytes.seek(0)
                log_message("Processing complete, output ready.")
                return out_bytes, (len(frame_list), fw, fh, dly, sc, filename)

            except Exception as e:
                log_message(f"Error in processing thread: {e}")
                raise e

        # -------- Run processing in a thread to avoid blocking --------
        try:
            log_message("Submitting processing task to thread pool...")
            result_bytes, info = await asyncio.to_thread(
                process_images,
                img_data,
                frame_width,
                frame_height,
                cols,
                rows,
                delay,
                start_frame,
                end_frame,
                scale,
                format,
                lossless,
                quality
            )
            log_message("Processing finished, preparing to send response...")
        except Exception as e:
            log_message(f"Processing failed: {e}")
            await interaction.followup.send(f"An error occurred: {e}")
            return

        # -------- Send result --------
        file = discord.File(result_bytes, filename=info[5])  # filename is in the last element
        frame_count, res_w, res_h, delay_ms, scale_factor, _ = info
        log_message(f"Sending result: {frame_count} frames, {res_w}×{res_h}, {delay_ms}ms, scale {scale_factor}x")
        await interaction.followup.send(
            content=(
                f"✅ Animation generated ({format.upper()}):\n"
                f"• Frames: {frame_count}\n"
                f"• Resolution: {res_w}×{res_h}\n"
                f"• Delay: {delay_ms} ms\n"
                f"• Scale: {scale_factor}×"
            ),
            file=file
        )
        log_message("Command completed successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SpritesheetToAnimation(bot))