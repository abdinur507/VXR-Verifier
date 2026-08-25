"""
/setupverification - configure everything (channels, roles, questions, cooldown, rejoin policy)
/verification        - (re)send the Somali verification panel to the configured channel
"""

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
from cogs.verification import VerificationPanelView, build_panel_embed


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="setupverification", description="Configure the JAMAAHIRTA GANG『𝑽𝑿𝑹』verification system")
    @app_commands.describe(
        verification_channel="Channel where the Somali verification panel is posted",
        review_channel="Private staff channel applications are sent to",
        log_channel="Channel where verification actions are logged",
        unverified_role="Role given to new/unverified members",
        verified_role="Role granted on acceptance",
        member_role="Second role granted on acceptance",
        staff_role="Role authorized to review applications and use staff commands",
        cooldown_minutes="Minutes a denied member must wait before re-applying",
        rejoin_policy="What happens when a previously verified member rejoins",
        question_1="Application question 1 (default: in-game name)",
        question_2="Application question 2 (optional)",
        question_3="Application question 3 (optional)",
        question_4="Application question 4 (optional)",
        question_5="Application question 5 (optional)",
    )
    @app_commands.choices(rejoin_policy=[
        app_commands.Choice(name="Permanent verification (default)", value="permanent"),
        app_commands.Choice(name="Require re-verification", value="reverify"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def setupverification(
        self,
        interaction: discord.Interaction,
        verification_channel: Optional[discord.TextChannel] = None,
        review_channel: Optional[discord.TextChannel] = None,
        log_channel: Optional[discord.TextChannel] = None,
        unverified_role: Optional[discord.Role] = None,
        verified_role: Optional[discord.Role] = None,
        member_role: Optional[discord.Role] = None,
        staff_role: Optional[discord.Role] = None,
        cooldown_minutes: Optional[int] = None,
        rejoin_policy: Optional[app_commands.Choice[str]] = None,
        question_1: Optional[str] = None,
        question_2: Optional[str] = None,
        question_3: Optional[str] = None,
        question_4: Optional[str] = None,
        question_5: Optional[str] = None,
    ):
        guild = interaction.guild
        existing = await self.bot.db.get_guild_config(guild.id) or {}

        def resolve_role(explicit: Optional[discord.Role], existing_key: str, default_id: int) -> Optional[int]:
            if explicit is not None:
                return explicit.id
            if existing.get(existing_key):
                return existing[existing_key]
            fallback = guild.get_role(default_id)
            return fallback.id if fallback else None

        def resolve_channel(explicit: Optional[discord.TextChannel], existing_key: str, default_id: int) -> Optional[int]:
            if explicit is not None:
                return explicit.id
            if existing.get(existing_key):
                return existing[existing_key]
            fallback = guild.get_channel(default_id)
            return fallback.id if fallback else None

        fields = {
            "verification_channel_id": resolve_channel(verification_channel, "verification_channel_id", 0),
            "review_channel_id": resolve_channel(review_channel, "review_channel_id", config.DEFAULT_REVIEW_CHANNEL_ID),
            "log_channel_id": resolve_channel(log_channel, "log_channel_id", config.DEFAULT_LOG_CHANNEL_ID),
            "unverified_role_id": resolve_role(unverified_role, "unverified_role_id", config.DEFAULT_UNVERIFIED_ROLE_ID),
            "verified_role_id": resolve_role(verified_role, "verified_role_id", config.DEFAULT_VERIFIED_ROLE_ID),
            "member_role_id": resolve_role(member_role, "member_role_id", config.DEFAULT_MEMBER_ROLE_ID),
            "staff_role_id": resolve_role(staff_role, "staff_role_id", 0),
            "cooldown_minutes": cooldown_minutes if cooldown_minutes is not None else existing.get("cooldown_minutes", config.DEFAULT_COOLDOWN_MINUTES),
            "rejoin_policy": rejoin_policy.value if rejoin_policy else existing.get("rejoin_policy", config.DEFAULT_REJOIN_POLICY),
        }

        new_questions = [q for q in [question_1, question_2, question_3, question_4, question_5] if q]
        if new_questions:
            fields["questions"] = new_questions
        elif existing.get("questions"):
            fields["questions"] = existing["questions"]
        else:
            fields["questions"] = config.DEFAULT_QUESTIONS

        cfg = await self.bot.db.upsert_guild_config(guild.id, **fields)

        def fmt_role(rid):
            r = guild.get_role(rid) if rid else None
            return r.mention if r else f"`{rid}`" if rid else "**not set**"

        def fmt_channel(cid):
            c = guild.get_channel(cid) if cid else None
            return c.mention if c else f"`{cid}`" if cid else "**not set**"

        embed = discord.Embed(title="✅ Verification System Configured", color=config.COLOR_ACCEPTED)
        embed.add_field(name="Verification channel", value=fmt_channel(cfg["verification_channel_id"]), inline=False)
        embed.add_field(name="Review channel", value=fmt_channel(cfg["review_channel_id"]), inline=False)
        embed.add_field(name="Log channel", value=fmt_channel(cfg["log_channel_id"]), inline=False)
        embed.add_field(name="Unverified role", value=fmt_role(cfg["unverified_role_id"]), inline=True)
        embed.add_field(name="Verified role", value=fmt_role(cfg["verified_role_id"]), inline=True)
        embed.add_field(name="Member role", value=fmt_role(cfg["member_role_id"]), inline=True)
        embed.add_field(name="Staff role", value=fmt_role(cfg["staff_role_id"]), inline=True)
        embed.add_field(name="Cooldown", value=f"{cfg['cooldown_minutes']} minutes", inline=True)
        embed.add_field(
            name="Rejoin policy",
            value="Permanent verification" if cfg["rejoin_policy"] == "permanent" else "Re-verification required",
            inline=True,
        )
        embed.add_field(name="Questions", value="\n".join(f"{i+1}. {q}" for i, q in enumerate(cfg["questions"])), inline=False)
        embed.set_footer(text="Run /verification to post the panel, if you haven't already.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @setupverification.error
    async def setupverification_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need Administrator permission to configure verification.", ephemeral=True
            )
        else:
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Something went wrong: {error}", ephemeral=True)
            else:
                await interaction.response.send_message(f"❌ Something went wrong: {error}", ephemeral=True)

    @app_commands.command(name="verification", description="(Re)send the verification panel to the configured channel")
    @app_commands.checks.has_permissions(administrator=True)
    async def verification(self, interaction: discord.Interaction):
        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        if not cfg or not cfg.get("verification_channel_id"):
            await interaction.response.send_message(
                "Run `/setupverification` first and set a verification channel.", ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(cfg["verification_channel_id"])
        if channel is None:
            await interaction.response.send_message("The configured verification channel no longer exists.", ephemeral=True)
            return

        try:
            await channel.send(embed=build_panel_embed(), view=VerificationPanelView())
        except discord.Forbidden:
            await interaction.response.send_message(
                f"I don't have permission to post in {channel.mention}.", ephemeral=True
            )
            return

        await interaction.response.send_message(f"✅ Verification panel posted in {channel.mention}.", ephemeral=True)

    @verification.error
    async def verification_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "❌ You need Administrator permission to do that.", ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
