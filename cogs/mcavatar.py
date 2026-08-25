import asyncio
import tempfile
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import locale_for, t
from utils.mcskin import get_player_image


class MinecraftAvatarCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.script_path = Path(__file__).resolve().parents[1] / "scripts" / "mcavatar.js"

    @app_commands.command(
        name="mcavatar",
        description=locale_str(
            "Generate a pixel-style Minecraft avatar",
            i18n_key="mcavatar.command_description",
        ),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        player=locale_str(
            "Minecraft username to use (optional if image is provided)",
            i18n_key="mcavatar.param.player",
        ),
        image=locale_str(
            "Skin image attachment (optional if player is provided)",
            i18n_key="mcavatar.param.image",
        ),
        scale=locale_str(
            "Final upscale factor (default 10)",
            i18n_key="mcavatar.param.scale",
        ),
        outline=locale_str(
            "Outline pixel width: 0=off, 1=1px, 2=2px",
            i18n_key="mcavatar.param.outline",
        ),
        outline_color=locale_str(
            "Outline color: auto / auto_darker / auto_lighter or hex (#000000)",
            i18n_key="mcavatar.param.outline_color",
        ),
        bg_color=locale_str(
            "Background color: auto / auto_lighter / auto_darker or hex (#ffffff)",
            i18n_key="mcavatar.param.bg_color",
        ),
        fill_background=locale_str(
            "Whether to fill the background",
            i18n_key="mcavatar.param.fill_background",
        ),
        upscale48=locale_str(
            "Upscale to 48x48 scaling",
            i18n_key="mcavatar.param.upscale48",
        ),
        average_color=locale_str(
            "Average color for auto outline/bg: hex (#ff0000) or auto",
            i18n_key="mcavatar.param.average_color",
        ),
    )
    @app_commands.choices(
        outline=[
            app_commands.Choice(
                name=locale_str("Off", i18n_key="mcavatar.choice.outline_off"),
                value=0,
            ),
            app_commands.Choice(
                name=locale_str("1px", i18n_key="mcavatar.choice.outline_1px"),
                value=1,
            ),
            app_commands.Choice(
                name=locale_str("2px", i18n_key="mcavatar.choice.outline_2px"),
                value=2,
            ),
        ]
    )
    async def mcavatar(
        self,
        interaction: discord.Interaction,
        player: Optional[str] = None,
        image: Optional[discord.Attachment] = None,
        scale: int = 10,
        outline: app_commands.Choice[int] = None,
        outline_color: Optional[str] = None,
        bg_color: Optional[str] = None,
        fill_background: bool = True,
        upscale48: bool = False,
        average_color: Optional[str] = None,
    ):
        await interaction.response.defer(thinking=True)
        locale = locale_for(interaction)

        if not player and not image:
            await interaction.followup.send(
                t("mcavatar.error.need_player_or_image", locale=locale),
                ephemeral=True,
            )
            return

        outline_val = outline.value if outline else 0

        try:
            if image:
                if not image.content_type or not image.content_type.startswith("image/"):
                    await interaction.followup.send(
                        t("mcavatar.error.invalid_image", locale=locale),
                        ephemeral=True,
                    )
                    return
                skin_data = await image.read()
                label = t("mcavatar.attachment_label", locale=locale)
            else:
                try:
                    skin_data = await asyncio.to_thread(
                        get_player_image, player, img_type="skin"
                    )
                    label = player
                except Exception as e:
                    await interaction.followup.send(
                        t("mcavatar.error.fetch_skin", locale=locale, error=e),
                        ephemeral=True,
                    )
                    return

            if average_color and average_color.lower() != "auto":
                ac = average_color.strip()
                if not (ac.startswith("#") and len(ac) in (4, 7)):
                    await interaction.followup.send(
                        t("mcavatar.error.invalid_average_color", locale=locale),
                        ephemeral=True,
                    )
                    return

            if not self.script_path.is_file():
                await interaction.followup.send(
                    t("mcavatar.error.script_not_found", locale=locale),
                    ephemeral=True,
                )
                return

            with tempfile.TemporaryDirectory() as tmp:
                tmp_path = Path(tmp)
                input_path = tmp_path / "skin.png"
                output_path = tmp_path / "avatar.png"
                input_path.write_bytes(skin_data)

                cmd = [
                    "node",
                    str(self.script_path),
                    str(input_path),
                    str(output_path),
                    "--scale",
                    str(scale),
                    "--outline",
                    str(outline_val),
                ]
                if outline_color:
                    cmd.extend(["--outline-color", outline_color])
                if bg_color:
                    cmd.extend(["--bg-color", bg_color])
                if fill_background:
                    cmd.append("--fill-background")
                if upscale48:
                    cmd.append("--upscale48")
                if average_color:
                    cmd.extend(["--average-color", average_color])

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode != 0:
                    err = (stderr or stdout or b"").decode("utf-8", errors="replace")
                    await interaction.followup.send(
                        t("mcavatar.error.processing", locale=locale, error=err),
                        ephemeral=True,
                    )
                    return

                if not output_path.is_file():
                    await interaction.followup.send(
                        t("mcavatar.error.processing", locale=locale, error="no output"),
                        ephemeral=True,
                    )
                    return

                data = output_path.read_bytes()

            file = discord.File(
                fp=__import__("io").BytesIO(data),
                filename="avatar.png",
            )
            await interaction.followup.send(
                content=t("mcavatar.success", locale=locale, player=label),
                file=file,
            )

        except Exception as e:
            await interaction.followup.send(
                t("mcavatar.error.unexpected", locale=locale, error=e),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(MinecraftAvatarCog(bot))
