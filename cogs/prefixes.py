"""
/staffprefix <user>        - apply the correct staff/leadership nickname
                              prefix (auto-detected from config.STAFF_ROLE_TABLE
                              if the target holds one of those roles, otherwise
                              falls back to the legacy 『𝑽𝑿𝑹・𝑺𝒕𝒂𝒇𝒇』 prefix)
/removestaffprefix <user>  - remove it and restore the normal 『𝑽𝑿𝑹』 prefix

See also cogs/staffroles.py for /staffroles, /prefixpreview and /prefixsync.
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import utils


class PrefixesCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="staffprefix", description="Give a staff member the Staff VXR nickname prefix")
    @app_commands.describe(user="The staff member to prefix")
    async def staffprefix(self, interaction: discord.Interaction, user: discord.Member):
        if not await utils.require_staff(self.bot, interaction):
            return

        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message("Run `/setupverification` first.", ephemeral=True)
            return

        # Prefer the centralized leadership/staff table — gives Owner/Boss/etc.
        # their own distinct prefix instead of forcing the generic staff one.
        leadership_entry = utils.get_highest_staff_role(user)

        staff_role = interaction.guild.get_role(cfg["staff_role_id"]) if cfg.get("staff_role_id") else None
        is_legacy_staff = staff_role and staff_role in user.roles
        is_target_staff = user.guild_permissions.administrator or leadership_entry is not None or is_legacy_staff
        if not is_target_staff:
            await interaction.response.send_message(
                f"{user.mention} doesn't hold a configured staff/leadership role, so they aren't "
                "eligible for a staff prefix.",
                ephemeral=True,
            )
            return

        if leadership_entry is not None:
            ok, msg = await utils.apply_configured_prefix(user)
        else:
            ok, msg = await utils.apply_staff_prefix(user)
        if ok:
            await self.bot.db.set_staff_prefix_flag(interaction.guild.id, user.id, True)
            log_embed = discord.Embed(title="🏷️ Staff Prefix Applied", color=config.COLOR_INFO)
            log_embed.add_field(name="Member", value=f"{user.mention} (`{user.id}`)", inline=False)
            log_embed.add_field(name="By", value=interaction.user.mention, inline=True)
            await utils.send_log(self.bot, interaction.guild, log_embed)
            await interaction.response.send_message(
                f"✅ **Staff Prefix Applied**\n{user.mention} has been given the Staff VXR prefix.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(f"❌ Couldn't update the nickname: {msg}", ephemeral=True)

    @app_commands.command(name="removestaffprefix", description="Remove the Staff VXR prefix and restore the normal one")
    @app_commands.describe(user="The member to update")
    async def removestaffprefix(self, interaction: discord.Interaction, user: discord.Member):
        if not await utils.require_staff(self.bot, interaction):
            return

        ok, msg = await utils.apply_member_prefix(user)
        if ok:
            await self.bot.db.set_staff_prefix_flag(interaction.guild.id, user.id, False)
            log_embed = discord.Embed(title="🏷️ Staff Prefix Removed", color=config.COLOR_INFO)
            log_embed.add_field(name="Member", value=f"{user.mention} (`{user.id}`)", inline=False)
            log_embed.add_field(name="By", value=interaction.user.mention, inline=True)
            await utils.send_log(self.bot, interaction.guild, log_embed)
            await interaction.response.send_message(
                f"✅ Staff prefix removed — {user.mention} now has the normal Verified prefix.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(f"❌ Couldn't update the nickname: {msg}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PrefixesCog(bot))
