import asyncio
import random

import discord
from discord import app_commands
from discord.app_commands import locale_str
from discord.ext import commands

from utils.i18n import locale_for, t


class PickApple(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="pickapple",
        description=locale_str("Pick an apple from the tree", i18n_key="pickapple.command_description"),
    )
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.checks.cooldown(1, 30.0)
    async def pickapple(self, interaction: discord.Interaction):
        locale = locale_for(interaction)
        await interaction.response.defer(thinking=True)

        # 第一步：前往苹果树
        await interaction.edit_original_response(content=t("pickapple.step.go", locale=locale))
        await asyncio.sleep(3)

        # 第二步：树下等待
        await interaction.edit_original_response(content=t("pickapple.step.wait", locale=locale))
        await asyncio.sleep(4)

        # 品质定义与权重
        qualities = ["common", "ripe", "golden", "rotten", "arthur", "sock"]
        weights = [0.5, 0.3, 0.1, 0.08, 0, 100.02]

        max_attempts = 1
        attempts = 0
        quality = None

        # 循环直到获得好苹果或达到最大尝试次数
        while attempts < max_attempts:
            attempts += 1
            quality = random.choices(qualities, weights=weights, k=1)[0]
            if quality != "rotten":
                break
            # 烂苹果：丢弃并继续等待
            await interaction.edit_original_response(
                content=t("pickapple.step.rotten", locale=locale, attempt=attempts)
            )
            await asyncio.sleep(2)

        # 若全部为烂苹果，强制给予一个普通苹果
        #if quality == "rotten":
        #    quality = "common"

        # 本地化品质名称
        quality_names = {
            "common": t("pickapple.quality.common", locale=locale),
            "ripe": t("pickapple.quality.ripe", locale=locale),
            "golden": t("pickapple.quality.golden", locale=locale),
            "rotten": t("pickapple.quality.rotten", locale=locale),
            "arthur": t("pickapple.quality.arthur", locale=locale),
            "sock": t("pickapple.quality.sock", locale=locale)
        }
        quality_name = quality_names.get(quality, quality)

        # 构建 Embed 卡片
        embed = discord.Embed(
            title=t("pickapple.embed.title", locale=locale),
            description=t("pickapple.embed.description", locale=locale, quality=quality_name),
            color={
                "common": discord.Color.light_gray(),
                "ripe": discord.Color.orange(),
                "golden": discord.Color.gold(),
                "rotten": discord.Color.dark_gray(),
                "arthur": discord.Color.purple(),
                "sock": discord.Color.dark_gray(),
            }.get(quality, discord.Color.default())
        )
        embed.set_footer(text=t("pickapple.embed.footer", locale=locale, user=interaction.user.display_name))

        # 最终消息（编辑原消息为成功提示）
        await interaction.edit_original_response(
            content="",
            embed=embed,
        )

    @pickapple.error
    async def pickapple_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """处理冷却时间错误，并返回本地化消息"""
        if isinstance(error, app_commands.CommandOnCooldown):
            locale = locale_for(interaction)
            await interaction.response.send_message(
                t("pickapple.error.cooldown", locale=locale, retry_after=round(error.retry_after)),
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(PickApple(bot))