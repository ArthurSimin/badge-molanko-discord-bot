import io
import asyncio
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Select
from PIL import Image


def log_message(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [spritesheet_animation] {msg}")


def process_images(data, fw, fh, c, r, dly, start, end, sc, fmt, loss, qual):
    try:
        log_message("Starting image processing in thread...")
        spritesheet = Image.open(io.BytesIO(data))
        log_message(f"Image opened: {spritesheet.size}, mode: {spritesheet.mode}")
        if spritesheet.mode not in ("RGBA", "RGB", "P"):
            spritesheet = spritesheet.convert("RGBA")
        elif spritesheet.mode == "P":
            spritesheet = spritesheet.convert("RGBA")

        sheet_w, sheet_h = spritesheet.size

        if c is None and r is None:
            c = sheet_w // fw
            r = sheet_h // fh
            if c == 0 or r == 0:
                raise ValueError(f"Frame size ({fw}×{fh}) larger than image ({sheet_w}×{sheet_h}).")
        elif c is None:
            max_frames = (sheet_w // fw) * (sheet_h // fh)
            c = max_frames // r
            if c == 0:
                raise ValueError(f"With {r} rows, columns would be 0.")
        elif r is None:
            total_frames = (sheet_w // fw) * (sheet_h // fh)
            r = total_frames // c
            if r == 0:
                raise ValueError(f"With {c} columns, rows would be 0.")

        max_c = sheet_w // fw
        max_r = sheet_h // fh
        if c > max_c:
            raise ValueError(f"Columns ({c}) exceed maximum {max_c}.")
        if r > max_r:
            raise ValueError(f"Rows ({r}) exceed maximum {max_r}.")

        total = c * r
        if start >= total:
            raise ValueError(f"Start frame {start} out of range (0–{total-1}).")
        if end is None:
            end = total - 1
        else:
            if end < start:
                raise ValueError("End frame must be >= start frame.")
            if end >= total:
                raise ValueError(f"End frame {end} exceeds maximum {total-1}.")

        frame_count = end - start + 1
        log_message(f"Extracting {frame_count} frames...")
        frame_list = []
        for idx in range(start, end + 1):
            col = idx % c
            row = idx // c
            left = col * fw
            top = row * fh
            frame = spritesheet.crop((left, top, left + fw, top + fh))
            frame_list.append(frame)

        if not frame_list:
            raise ValueError("No frames extracted.")

        if sc != 1:
            log_message(f"Scaling frames by {sc}x...")
            new_size = (fw * sc, fh * sc)
            scaled = []
            for f in frame_list:
                scaled.append(f.resize(new_size, Image.NEAREST))
            frame_list = scaled
            fw, fh = new_size

        out_bytes = io.BytesIO()
        if fmt == "gif":
            log_message("Preparing GIF with per-frame palettes...")
            gif_frames = []
            for img in frame_list:
                rgb = img.convert("RGB")
                quantized = rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.FLOYDSTEINBERG)
                gif_frames.append(quantized)

            gif_frames[0].save(
                out_bytes,
                format="GIF",
                save_all=True,
                append_images=gif_frames[1:],
                loop=0,
                duration=dly,
                optimize=False,
                disposal=2,
                palette=None
            )
            filename = "animation.gif"
        else:  # webp
            log_message("Preparing WebP...")
            mode = "RGBA" if frame_list[0].mode == "RGBA" else "RGB"
            webp_frames = [f.convert(mode) for f in frame_list]
            webp_frames[0].save(
                out_bytes,
                format="WEBP",
                save_all=True,
                append_images=webp_frames[1:],
                loop=0,
                duration=dly,
                lossless=loss,
                quality=qual,
                method=4
            )
            filename = "animation.webp"

        out_bytes.seek(0)
        log_message("Processing complete.")
        return out_bytes, (len(frame_list), fw, fh, dly, sc, filename)

    except Exception as e:
        log_message(f"Error in processing thread: {e}")
        raise e


class SpritesheetModal(Modal):
    def __init__(self, image: discord.Attachment, output_format: str):
        super().__init__(title="Spritesheet Settings")
        self.image = image
        self.output_format = output_format

    frame_width = TextInput(label="Frame Width (px)", default="32", required=True)
    frame_height = TextInput(label="Frame Height (px)", default="32", required=True)
    delay = TextInput(label="Delay (ms)", default="100", required=True)
    scale = TextInput(label="Scale (1-8)", default="2", required=True)
    advanced = TextInput(
        label="Advanced (optional)",
        placeholder="start=0 end=10 lossless=true quality=90",
        required=False,
        default=""
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Parse basic
        try:
            fw = int(self.frame_width.value)
            fh = int(self.frame_height.value)
            dly = int(self.delay.value)
            sc = int(self.scale.value)
        except ValueError as e:
            await interaction.response.send_message(f"Invalid number: {e}", ephemeral=True)
            return

        if fw < 1 or fh < 1:
            await interaction.response.send_message("Width and height must be ≥1.", ephemeral=True)
            return
        if dly < 10:
            await interaction.response.send_message("Delay must be ≥10 ms.", ephemeral=True)
            return
        if sc < 1 or sc > 8:
            await interaction.response.send_message("Scale must be between 1 and 8.", ephemeral=True)
            return

        # Defaults
        start = 0
        end = None
        lossless = False
        quality = 80

        # Parse advanced string
        if self.advanced.value.strip():
            for token in self.advanced.value.split():
                if '=' in token:
                    key, val = token.split('=', 1)
                    key = key.strip().lower()
                    val = val.strip()
                    if key == 'start':
                        try:
                            start = int(val)
                            if start < 0:
                                start = 0
                        except:
                            pass
                    elif key == 'end':
                        try:
                            end = int(val)
                        except:
                            pass
                    elif key == 'lossless':
                        lossless = val.lower() in ('true', '1', 'yes')
                    elif key == 'quality':
                        try:
                            q = int(val)
                            if 1 <= q <= 100:
                                quality = q
                        except:
                            pass

        log_message(f"Modal: format={self.output_format}, fw={fw}, fh={fh}, dly={dly}, start={start}, end={end}, sc={sc}, lossless={lossless}, quality={quality}")

        await interaction.response.defer(thinking=True)
        try:
            img_data = await self.image.read()
        except Exception as e:
            await interaction.followup.send(f"Failed to read image: {e}")
            return

        try:
            result_bytes, info = await asyncio.to_thread(
                process_images,
                img_data,
                fw,
                fh,
                None, None,
                dly,
                start,
                end,
                sc,
                self.output_format,
                lossless,
                quality
            )
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")
            return

        file = discord.File(result_bytes, filename=info[5])
        frame_count, res_w, res_h, delay_ms, scale_factor, _ = info
        await interaction.followup.send(
            content=(
                f"✅ Animation generated ({self.output_format.upper()}):\n"
                f"• Frames: {frame_count}\n"
                f"• Resolution: {res_w}×{res_h}\n"
                f"• Delay: {delay_ms} ms\n"
                f"• Scale: {scale_factor}×"
            ),
            file=file
        )
        log_message("Modal processing finished.")


class FormatSelectView(View):
    def __init__(self, image_attachment):
        super().__init__(timeout=60)
        self.image = image_attachment
        self.format = "gif"

    @discord.ui.select(placeholder="Select output format", options=[
        discord.SelectOption(label="GIF", value="gif", description="Per-frame palettes", emoji="🖼️"),
        discord.SelectOption(label="WebP", value="webp", description="Modern format", emoji="🌐")
    ])
    async def select_format(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.format = select.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Next →", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = SpritesheetModal(image=self.image, output_format=self.format)
        await interaction.response.send_modal(modal)
        self.stop()


class SpritesheetToAnimation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name="Extract Spritesheet",
            callback=self.extract_spritesheet_context,
        )
        try:
            self.bot.tree.remove_command("Extract Spritesheet", type=app_commands.CommandType.MESSAGE)
        except:
            pass
        self.bot.tree.add_command(self.ctx_menu)
        log_message("Context menu 'Extract Spritesheet' registered.")

    def cog_unload(self):
        try:
            self.bot.tree.remove_command("Extract Spritesheet", type=app_commands.CommandType.MESSAGE)
            log_message("Context menu 'Extract Spritesheet' removed.")
        except:
            pass

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
        scale="Upscale factor (1‑8, default 2)",
        format="Output format: 'gif' or 'webp' (default gif)",
        lossless="For WebP: enable lossless compression (default False)",
        quality="For WebP: quality 1‑100 (default 80)"
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
        log_message(f"Slash command invoked by {interaction.user}")

        if frame_width < 1 or frame_height < 1:
            await interaction.followup.send("Width and height must be ≥1.")
            return
        if delay < 10:
            await interaction.followup.send("Delay must be ≥10 ms.")
            return
        if start_frame < 0:
            await interaction.followup.send("Start frame cannot be negative.")
            return
        if scale < 1 or scale > 8:
            await interaction.followup.send("Scale must be between 1 and 8.")
            return
        if format not in ("gif", "webp"):
            await interaction.followup.send("Format must be 'gif' or 'webp'.")
            return
        if quality < 1 or quality > 100:
            await interaction.followup.send("Quality must be between 1 and 100.")
            return
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.followup.send("Please upload a valid image file.")
            return

        try:
            img_data = await image.read()
        except Exception as e:
            await interaction.followup.send(f"Failed to read image: {e}")
            return

        try:
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
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")
            return

        file = discord.File(result_bytes, filename=info[5])
        frame_count, res_w, res_h, delay_ms, scale_factor, _ = info
        extra = f"\n• Lossless: {lossless}\n• Quality: {quality}" if format == "webp" else ""
        await interaction.followup.send(
            content=(
                f"✅ Animation generated ({format.upper()}):\n"
                f"• Frames: {frame_count}\n"
                f"• Resolution: {res_w}×{res_h}\n"
                f"• Delay: {delay_ms} ms\n"
                f"• Scale: {scale_factor}×"
                + extra
            ),
            file=file
        )

    async def extract_spritesheet_context(self, interaction: discord.Interaction, message: discord.Message):
        log_message(f"Context menu invoked by {interaction.user} on message {message.id}")

        image_attachment = None
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                image_attachment = att
                break

        if not image_attachment:
            await interaction.response.send_message("No image attachment found.", ephemeral=True)
            return

        view = FormatSelectView(image_attachment)
        await interaction.response.send_message(
            "Select output format, then click **Next** to continue.",
            view=view,
            ephemeral=True
        )
        log_message("Format selection view sent.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SpritesheetToAnimation(bot))