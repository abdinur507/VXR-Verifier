"""
Slash commands for browsing and manually resolving applications:
  /applications        - list pending applications
  /application <id>    - view one application in detail
  /accept <user>        - manually approve (bypasses the modal flow)
  /deny <user> <reason>  - manually deny (bypasses the modal flow)
"""

import discord
from discord import app_commands
from discord.ext import commands

import config
import utils


class ApplicationsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="applications", description="Show pending applications, or one member's application history")
    @app_commands.describe(user="Optional — show this member's application history instead of the pending queue")
    async def applications(self, interaction: discord.Interaction, user: discord.Member = None):
        if not await utils.require_staff(self.bot, interaction):
            return

        if user is not None:
            history = await self.bot.db.list_applications_by_user(interaction.guild.id, user.id)
            if not history:
                await interaction.response.send_message(
                    f"{user.mention} has no application history.", ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"📜 Application History — {user.display_name}",
                color=config.COLOR_INFO,
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            for app in history[:25]:
                first_answer = next(iter(app["answers"].values()), "-")
                status_emoji = config.STATUS_EMOJI.get(app["status"], "")
                reviewer = f" — reviewed by <@{app['reviewer_id']}>" if app.get("reviewer_id") else ""
                value = f"{status_emoji} **{app['status'].capitalize()}**{reviewer}\n\"{first_answer[:80]}\""
                if app.get("deny_reason"):
                    value += f"\nReason: {app['deny_reason'][:150]}"
                embed.add_field(name=utils.format_app_id(app["id"]), value=value, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        pending = await self.bot.db.list_pending_applications(interaction.guild.id)
        if not pending:
            await interaction.response.send_message("There are no pending applications. 🎉", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🟡 Pending Applications ({len(pending)})",
            color=config.COLOR_PENDING,
        )
        for app in pending[:25]:
            first_answer = next(iter(app["answers"].values()), "-")
            embed.add_field(
                name=utils.format_app_id(app["id"]),
                value=f"<@{app['user_id']}> — \"{first_answer[:60]}\"",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="application", description="View a specific application by ID")
    @app_commands.describe(id="The application ID number, e.g. 12")
    async def application(self, interaction: discord.Interaction, id: int):
        if not await utils.require_staff(self.bot, interaction):
            return

        app = await self.bot.db.get_application(id)
        if not app or app["guild_id"] != interaction.guild.id:
            await interaction.response.send_message("No application found with that ID.", ephemeral=True)
            return

        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        try:
            applicant = interaction.guild.get_member(app["user_id"]) or await self.bot.fetch_user(app["user_id"])
        except discord.NotFound:
            applicant = None

        if applicant is None:
            await interaction.response.send_message(
                f"Application {utils.format_app_id(id)} belongs to a user I can no longer find "
                f"(ID `{app['user_id']}`).",
                ephemeral=True,
            )
            return

        embed = utils.build_review_embed(applicant, app, cfg["questions"] if cfg else config.DEFAULT_QUESTIONS)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="accept", description="Manually approve a member's verification")
    @app_commands.describe(user="The member to verify")
    async def accept(self, interaction: discord.Interaction, user: discord.Member):
        if not await utils.require_staff(self.bot, interaction):
            return

        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message("Run `/setupverification` first.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        application = await self.bot.db.get_latest_application(interaction.guild.id, user.id)
        if application and application["status"] == "pending":
            finalized = await self.bot.db.finalize_application(application["id"], "accepted", interaction.user.id)
            if not finalized:
                await interaction.followup.send("⚠️ That application was already processed.")
                return
            application = await self.bot.db.get_application(application["id"])
        else:
            app_id = await self.bot.db.create_application(
                interaction.guild.id, user.id, {"q0": "Manually accepted by staff without a submitted application."}
            )
            await self.bot.db.finalize_application(app_id, "accepted", interaction.user.id)
            application = await self.bot.db.get_application(app_id)

        warnings = await utils.process_acceptance(self.bot, interaction.guild, user, interaction.user, application)

        msg = f"✅ {user.mention} has been verified ({utils.format_app_id(application['id'])})."
        if warnings:
            msg += "\n⚠️ " + "\n⚠️ ".join(warnings)
        await interaction.followup.send(msg)

    @app_commands.command(name="deny", description="Manually deny a member's verification")
    @app_commands.describe(user="The member to deny", reason="Reason shown to the applicant")
    async def deny(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        if not await utils.require_staff(self.bot, interaction):
            return

        cfg = await self.bot.db.get_guild_config(interaction.guild.id)
        if not cfg:
            await interaction.response.send_message("Run `/setupverification` first.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        application = await self.bot.db.get_latest_application(interaction.guild.id, user.id)
        if application and application["status"] == "pending":
            finalized = await self.bot.db.finalize_application(
                application["id"], "denied", interaction.user.id, deny_reason=reason
            )
            if not finalized:
                await interaction.followup.send("⚠️ That application was already processed.")
                return
            application = await self.bot.db.get_application(application["id"])
        else:
            app_id = await self.bot.db.create_application(
                interaction.guild.id, user.id, {"q0": "Manually denied by staff without a submitted application."}
            )
            await self.bot.db.finalize_application(app_id, "denied", interaction.user.id, deny_reason=reason)
            application = await self.bot.db.get_application(app_id)

        warnings = await utils.process_denial(self.bot, interaction.guild, user, interaction.user, reason, application)

        msg = f"🔴 {user.mention}'s verification was denied ({utils.format_app_id(application['id'])})."
        if warnings:
            msg += "\n⚠️ " + "\n⚠️ ".join(warnings)
        await interaction.followup.send(msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(ApplicationsCog(bot))
