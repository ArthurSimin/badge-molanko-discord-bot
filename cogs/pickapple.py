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

        # 第二步：树下等待 – 随机选择一条消息（.4 概率较低）
        wait_keys = [
            "pickapple.step.wait.1",
            "pickapple.step.wait.2",
            "pickapple.step.wait.3",
            "pickapple.step.wait.4",
        ]
        wait_weights = [0.3, 0.3, 0.3, 0.1]  # .4 只有 10% 概率
        selected_wait_key = random.choices(wait_keys, weights=wait_weights, k=1)[0]
        await interaction.edit_original_response(content=t(selected_wait_key, locale=locale))
        await asyncio.sleep(4)

        # 品质与权重（含新增的 watermelon 和 air）
        qualities = ["common", "ripe", "golden", "rotten", "arthur", "sock", "watermelon", "air"]
        weights = [0.5, 0.3, 0.1, 0.1, 0, 0.02, 0.02, 0.1]

        # 只尝试一次（按你的设定）
        quality = random.choices(qualities, weights=weights, k=1)[0]

        # 如果是烂苹果，可能触发隐藏消息（10% 概率）
        if quality == "rotten":
            if random.random() < 0.1:
                rotten_key = "pickapple.step.rotten.hidden"
            else:
                rotten_key = "pickapple.step.rotten"
            await interaction.edit_original_response(
                content=t(rotten_key, locale=locale, attempt=1)  # 此处 attempt 为固定值 1
            )
            await asyncio.sleep(2)

        # 所有品质的本地化名称
        quality_names = {
            "common": t("pickapple.quality.common", locale=locale),
            "ripe": t("pickapple.quality.ripe", locale=locale),
            "golden": t("pickapple.quality.golden", locale=locale),
            "rotten": t("pickapple.quality.rotten", locale=locale),
            "arthur": t("pickapple.quality.arthur", locale=locale),
            "sock": t("pickapple.quality.sock", locale=locale),
            "watermelon": t("pickapple.quality.watermelon", locale=locale),
            "air": t("pickapple.quality.air", locale=locale),
        }
        quality_name = quality_names.get(quality, quality)

        # 颜色映射（新增 watermelon 和 air 的颜色）
        color_map = {
            "common": discord.Color.light_gray(),
            "ripe": discord.Color.orange(),
            "golden": discord.Color.gold(),
            "rotten": discord.Color.dark_gray(),
            "arthur": discord.Color.purple(),
            "sock": discord.Color.dark_gray(),
            "watermelon": discord.Color.green(),
            "air": discord.Color.blue(),
        }
        embed_color = color_map.get(quality, discord.Color.default())

        # 构建 Embed 卡片
        embed = discord.Embed(
            title=t("pickapple.embed.title", locale=locale),
            description=t("pickapple.embed.description", locale=locale, quality=quality_name),
            color=embed_color,
        )
        embed.set_footer(text=t("pickapple.embed.footer", locale=locale, user=interaction.user.display_name))

        # 最终编辑消息（清空文字，仅显示 Embed）
        await interaction.edit_original_response(content="", embed=embed)

    @pickapple.error
    async def pickapple_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """冷却时间错误处理"""
        if isinstance(error, app_commands.CommandOnCooldown):
            locale = locale_for(interaction)
            await interaction.response.send_message(
                t("pickapple.error.cooldown", locale=locale, retry_after=round(error.retry_after)),
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(PickApple(bot))
