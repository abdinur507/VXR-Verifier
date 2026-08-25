"""
/verify <user>        - directly grant verification (no application needed)
/unverify <user>      - strip verification and return the member to Unverified
/verificationlogs      - stats snapshot for this guild
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import utils


class ModerationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="verify", description="Manually verify a member (no application required)")
    @app_commands.describe(user="The member to verify")
    async def verify(self, interaction: discord.Interaction, user: discord.Member):
        if not await utils.require_staff(self.bot, interaction):
            return

        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message("Run `/setupverification` first.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        warnings = await utils.process_acceptance(self.bot, interaction.guild, user, interaction.user, None)

        msg = f"✅ {user.mention} has been manually verified."
        if warnings:
            msg += "\n⚠️ " + "\n⚠️ ".join(warnings)
        await interaction.followup.send(msg)

    @app_commands.command(name="unverify", description="Remove verification and return a member to Unverified")
    @app_commands.describe(user="The member to unverify")
    async def unverify(self, interaction: discord.Interaction, user: discord.Member):
        if not await utils.require_staff(self.bot, interaction):
            return

        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message("Run `/setupverification` first.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        warnings = await utils.process_unverify(self.bot, interaction.guild, user, interaction.user)

        msg = f"🔒 {user.mention} has been returned to Unverified."
        if warnings:
            msg += "\n⚠️ " + "\n⚠️ ".join(warnings)
        await interaction.followup.send(msg)

    @app_commands.command(name="verificationlogs", description="View verification statistics for this server")
    async def verificationlogs(self, interaction: discord.Interaction):
        if not await utils.require_staff(self.bot, interaction):
            return

        stats = await self.bot.db.stats(interaction.guild.id)
        cfg = await self.bot.db.get_guild_config(interaction.guild.id)

        embed = discord.Embed(title="📊 Verification Statistics", color=config.COLOR_INFO)
        embed.add_field(name="🟡 Pending", value=str(stats["pending"]), inline=True)
        embed.add_field(name="🟢 Accepted", value=str(stats["accepted"]), inline=True)
        embed.add_field(name="🔴 Denied", value=str(stats["denied"]), inline=True)
        embed.add_field(name="Total applications", value=str(stats["total"]), inline=False)
        if cfg:
            embed.add_field(
                name="Rejoin policy",
                value="Permanent verification" if cfg["rejoin_policy"] == "permanent" else "Re-verification required",
                inline=True,
            )
            embed.add_field(name="Cooldown", value=f"{cfg['cooldown_minutes']} minutes", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationCog(bot))
