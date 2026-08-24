import io
import asyncio
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands
from discord.ui import Modal, TextInput, View
from PIL import Image

from utils.i18n import locale_for, t


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
                raise ValueError(f"Frame size ({fw}x{fh}) larger than image ({sheet_w}x{sheet_h}).")
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
            raise ValueError(f"Start frame {start} out of range (0-{total-1}).")
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
                quantized = rgb.quantize(
                    colors=256,
                    method=Image.Quantize.MEDIANCUT,
                    dither=Image.Dither.FLOYDSTEINBERG,
                )
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
                palette=None,
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
                method=4,
            )
            filename = "animation.webp"

        out_bytes.seek(0)
        log_message("Processing complete.")
        return out_bytes, (len(frame_list), fw, fh, dly, sc, filename)

    except Exception as e:
        log_message(f"Error in processing thread: {e}")
        raise e


class SpritesheetModal(Modal):
    def __init__(self, image: discord.Attachment, output_format: str, locale: str | None = None):
        super().__init__(title=t("spritesheet.modal.title", locale=locale))
        self.image = image
        self.output_format = output_format
        self.locale = locale

        self.frame_width = TextInput(
            label=t("spritesheet.modal.frame_width", locale=locale),
            default="32",
            required=True,
        )
        self.frame_height = TextInput(
            label=t("spritesheet.modal.frame_height", locale=locale),
            default="32",
            required=True,
        )
        self.delay = TextInput(
            label=t("spritesheet.modal.delay", locale=locale),
            default="100",
            required=True,
        )
        self.scale = TextInput(
            label=t("spritesheet.modal.scale", locale=locale),
            default="2",
            required=True,
        )
        self.advanced = TextInput(
            label=t("spritesheet.modal.advanced", locale=locale),
            placeholder=t("spritesheet.modal.advanced_placeholder", locale=locale),
            required=False,
            default="",
        )

        self.add_item(self.frame_width)
        self.add_item(self.frame_height)
        self.add_item(self.delay)
        self.add_item(self.scale)
        self.add_item(self.advanced)

    async def on_submit(self, interaction: discord.Interaction):
        locale = self.locale or locale_for(interaction)

        try:
            fw = int(self.frame_width.value)
            fh = int(self.frame_height.value)
            dly = int(self.delay.value)
            sc = int(self.scale.value)
        except ValueError as e:
            await interaction.response.send_message(
                t("spritesheet.error.invalid_number", locale=locale, error=e),
                ephemeral=True,
            )
            return

        if fw < 1 or fh < 1:
            await interaction.response.send_message(
                t("spritesheet.error.size_min", locale=locale),
                ephemeral=True,
            )
            return
        if dly < 10:
            await interaction.response.send_message(
                t("spritesheet.error.delay_min", locale=locale),
                ephemeral=True,
            )
            return
        if sc < 1 or sc > 8:
            await interaction.response.send_message(
                t("spritesheet.error.scale_range", locale=locale),
                ephemeral=True,
            )
            return

        start = 0
        end = None
        lossless = False
        quality = 80

        if self.advanced.value.strip():
            for token in self.advanced.value.split():
                if "=" in token:
                    key, val = token.split("=", 1)
                    key = key.strip().lower()
                    val = val.strip()
                    if key == "start":
                        try:
                            start = int(val)
                            if start < 0:
                                start = 0
                        except Exception:
                            pass
                    elif key == "end":
                        try:
                            end = int(val)
                        except Exception:
                            pass
                    elif key == "lossless":
                        lossless = val.lower() in ("true", "1", "yes")
                    elif key == "quality":
                        try:
                            q = int(val)
                            if 1 <= q <= 100:
                                quality = q
                        except Exception:
                            pass

        log_message(
            f"Modal: format={self.output_format}, fw={fw}, fh={fh}, dly={dly}, "
            f"start={start}, end={end}, sc={sc}, lossless={lossless}, quality={quality}"
        )

        await interaction.response.defer(thinking=True)
        try:
            img_data = await self.image.read()
        except Exception as e:
            await interaction.followup.send(
                t("spritesheet.error.read_image", locale=locale, error=e)
            )
            return

        try:
            result_bytes, info = await asyncio.to_thread(
                process_images,
                img_data,
                fw,
                fh,
                None,
                None,
                dly,
                start,
                end,
                sc,
                self.output_format,
                lossless,
                quality,
            )
        except Exception as e:
            await interaction.followup.send(
                t("spritesheet.error.generic", locale=locale, error=e)
            )
            return

        file = discord.File(result_bytes, filename=info[5])
        frame_count, res_w, res_h, delay_ms, scale_factor, _ = info
        await interaction.followup.send(
            content=t(
                "spritesheet.success",
                locale=locale,
                format=self.output_format.upper(),
                frame_count=frame_count,
                res_w=res_w,
                res_h=res_h,
                delay_ms=delay_ms,
                scale_factor=scale_factor,
            ),
            file=file,
        )
        log_message("Modal processing finished.")


class FormatSelectView(View):
    def __init__(self, image_attachment, locale: str | None = None):
        super().__init__(timeout=60)
        self.image = image_attachment
        self.format = "gif"
        self.locale = locale

        select = discord.ui.Select(
            placeholder=t("spritesheet.view.format_placeholder", locale=locale),
            options=[
                discord.SelectOption(
                    label=t("spritesheet.view.format_gif_label", locale=locale),
                    value="gif",
                    description=t("spritesheet.view.format_gif_desc", locale=locale),
                    emoji="🖼️",
                ),
                discord.SelectOption(
                    label=t("spritesheet.view.format_webp_label", locale=locale),
                    value="webp",
                    description=t("spritesheet.view.format_webp_desc", locale=locale),
                    emoji="🌐",
                ),
            ],
        )
        select.callback = self.select_format
        self.add_item(select)

        button = discord.ui.Button(
            label=t("spritesheet.view.next_button", locale=locale),
            style=discord.ButtonStyle.primary,
        )
        button.callback = self.next_button
        self.add_item(button)

    async def select_format(self, interaction: discord.Interaction):
        select = interaction.data.get("values") if interaction.data else None
        if select:
            self.format = select[0]
        else:
            for child in self.children:
                if isinstance(child, discord.ui.Select) and child.values:
                    self.format = child.values[0]
                    break
        await interaction.response.defer()

    async def next_button(self, interaction: discord.Interaction):
        for child in self.children:
            if isinstance(child, discord.ui.Select) and child.values:
                self.format = child.values[0]
                break
        # Refresh locale in case preference changed; prefer stored locale from open
        locale = self.locale or locale_for(interaction)
        modal = SpritesheetModal(
            image=self.image,
            output_format=self.format,
            locale=locale,
        )
        await interaction.response.send_modal(modal)
        self.stop()


class SpritesheetToAnimation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name=locale_str(
                "Extract Spritesheet",
                i18n_key="spritesheet.context_name",
            ),
            callback=self.extract_spritesheet_context,
        )
        try:
            self.bot.tree.remove_command(
                "Extract Spritesheet", type=app_commands.CommandType.MESSAGE
            )
        except Exception:
            pass
        self.bot.tree.add_command(self.ctx_menu)
        log_message("Context menu 'Extract Spritesheet' registered.")

    def cog_unload(self):
        try:
            self.bot.tree.remove_command(
                "Extract Spritesheet", type=app_commands.CommandType.MESSAGE
            )
            log_message("Context menu 'Extract Spritesheet' removed.")
        except Exception:
            pass

    @app_commands.command(
        name="spritesheet_to_animation",
        description=locale_str(
            "Extract frames from a spritesheet as GIF or WebP",
            i18n_key="spritesheet.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        image=locale_str(
            "The spritesheet image (PNG/GIF/WebP)",
            i18n_key="spritesheet.param.image",
        ),
        frame_width=locale_str(
            "Width of each frame in pixels (default 32)",
            i18n_key="spritesheet.param.frame_width",
        ),
        frame_height=locale_str(
            "Height of each frame in pixels (default 32)",
            i18n_key="spritesheet.param.frame_height",
        ),
        cols=locale_str(
            "Columns (frames per row); auto if omitted",
            i18n_key="spritesheet.param.cols",
        ),
        rows=locale_str(
            "Number of rows; auto if omitted",
            i18n_key="spritesheet.param.rows",
        ),
        delay=locale_str(
            "Delay between frames in ms (default 100)",
            i18n_key="spritesheet.param.delay",
        ),
        start_frame=locale_str(
            "First frame index (0-based, default 0)",
            i18n_key="spritesheet.param.start_frame",
        ),
        end_frame=locale_str(
            "Last frame index (inclusive); omit for all",
            i18n_key="spritesheet.param.end_frame",
        ),
        scale=locale_str(
            "Upscale factor (1-8, default 2)",
            i18n_key="spritesheet.param.scale",
        ),
        format=locale_str(
            "Output format: gif or webp (default gif)",
            i18n_key="spritesheet.param.format",
        ),
        lossless=locale_str(
            "WebP: enable lossless compression",
            i18n_key="spritesheet.param.lossless",
        ),
        quality=locale_str(
            "WebP quality 1-100 (default 80)",
            i18n_key="spritesheet.param.quality",
        ),
    )
    @app_commands.choices(
        format=[
            app_commands.Choice(
                name=locale_str("GIF", i18n_key="spritesheet.choice.gif"),
                value="gif",
            ),
            app_commands.Choice(
                name=locale_str("WebP", i18n_key="spritesheet.choice.webp"),
                value="webp",
            ),
        ]
    )
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
        quality: int = 80,
    ):
        await interaction.response.defer(thinking=True)
        locale = locale_for(interaction)
        log_message(f"Slash command invoked by {interaction.user}")

        if frame_width < 1 or frame_height < 1:
            await interaction.followup.send(
                t("spritesheet.error.size_min", locale=locale)
            )
            return
        if delay < 10:
            await interaction.followup.send(
                t("spritesheet.error.delay_min", locale=locale)
            )
            return
        if start_frame < 0:
            await interaction.followup.send(
                t("spritesheet.error.start_negative", locale=locale)
            )
            return
        if scale < 1 or scale > 8:
            await interaction.followup.send(
                t("spritesheet.error.scale_range", locale=locale)
            )
            return
        if format not in ("gif", "webp"):
            await interaction.followup.send(
                t("spritesheet.error.format", locale=locale)
            )
            return
        if quality < 1 or quality > 100:
            await interaction.followup.send(
                t("spritesheet.error.quality_range", locale=locale)
            )
            return
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.followup.send(
                t("spritesheet.error.invalid_image", locale=locale)
            )
            return

        try:
            img_data = await image.read()
        except Exception as e:
            await interaction.followup.send(
                t("spritesheet.error.read_image", locale=locale, error=e)
            )
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
                quality,
            )
        except Exception as e:
            await interaction.followup.send(
                t("spritesheet.error.generic", locale=locale, error=e)
            )
            return

        file = discord.File(result_bytes, filename=info[5])
        frame_count, res_w, res_h, delay_ms, scale_factor, _ = info
        content = t(
            "spritesheet.success",
            locale=locale,
            format=format.upper(),
            frame_count=frame_count,
            res_w=res_w,
            res_h=res_h,
            delay_ms=delay_ms,
            scale_factor=scale_factor,
        )
        if format == "webp":
            content += t(
                "spritesheet.success_webp_extra",
                locale=locale,
                lossless=lossless,
                quality=quality,
            )
        await interaction.followup.send(content=content, file=file)

    async def extract_spritesheet_context(
        self, interaction: discord.Interaction, message: discord.Message
    ):
        locale = locale_for(interaction)
        log_message(
            f"Context menu invoked by {interaction.user} on message {message.id}"
        )

        image_attachment = None
        for att in message.attachments:
            if att.content_type and att.content_type.startswith("image/"):
                image_attachment = att
                break

        if not image_attachment:
            await interaction.response.send_message(
                t("spritesheet.context.no_image", locale=locale),
                ephemeral=True,
            )
            return

        view = FormatSelectView(image_attachment, locale=locale)
        await interaction.response.send_message(
            t("spritesheet.context.prompt", locale=locale),
            view=view,
            ephemeral=True,
        )
        log_message("Format selection view sent.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SpritesheetToAnimation(bot))
