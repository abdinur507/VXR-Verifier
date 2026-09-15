"""
Core verification flow:
  - on_member_join: assigns Unverified (or restores Verified+Member for
    returning members, depending on the guild's rejoin policy).
  - VerificationPanelView: the persistent "✅ Apply" button.
  - VerificationModal: the application form (question count is configurable).
  - ReviewView: the persistent "✅ Accept" / "❌ Deny" buttons on each
    application embed in the staff review channel.
"""

import logging
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands

import config
import utils

log = logging.getLogger("vxr-verifier")

SOMALI_PANEL_TEXT = (
    "**Ku soo dhawoow JAMAAHIRTA GANG! 🏴**\n\n"
    "Si aad u hesho gelitaanka server-ka, waa inaad marka hore **buuxisaa codsiga "
    "verification-ka**.\n\n"
    "Fadlan hubi inaad bixiso **xog sax ah oo ku saabsan magacaaga In-Game**, "
    "sababtoo ah Staff-ka ayaa dib u eegi doona codsigaaga.\n\n"
    "📝 Guji **Apply** si aad u bilowdo codsiga.\n\n"
    "⏳ Kadib markaad gudbiso codsigaaga, fadlan sug inta Staff-ku ay dib u eegayaan.\n\n"
    "✅ Haddii lagu aqbalo, **Unverified** waa lagaa saari doonaa waxaana si toos ah "
    "laguugu dari doonaa **Verified** iyo **Member** roles.\n\n"
    "❌ Haddii codsigaaga la diido, waxaa laguugu soo diri doonaa sababta diidmada.\n\n"
    "**⚠️ Ha dirin xog been ah ama xog qof kale leeyahay.**"
)


def build_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🔐 𝑱𝑨𝑴𝑨𝑨𝑯𝑰𝑹𝑻𝑨 𝑮𝑨𝑵𝑮 • 𝑽𝑬𝑹𝑰𝑭𝑰𝑪𝑨𝑻𝑰𝑶𝑵",
        description=SOMALI_PANEL_TEXT,
        color=config.COLOR_INFO,
    )
    embed.set_footer(text="JAMAAHIRTA GANG 『𝑽𝑿𝑹』 • Verification System")
    return embed


class VerificationModal(discord.ui.Modal, title="JAMAAHIRTA GANG Verification"):
    def __init__(self, questions: list[str]):
        super().__init__(timeout=600)
        self.field_map: list[discord.ui.TextInput] = []
        for i, q in enumerate(questions[: config.MAX_QUESTIONS]):
            field = discord.ui.TextInput(
                label=q[:45],
                style=discord.TextStyle.paragraph if len(q) > 45 else discord.TextStyle.short,
                required=True,
                max_length=500,
            )
            self.add_item(field)
            self.field_map.append(field)

    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        guild = interaction.guild
        cfg = await bot.db.get_guild_config(guild.id)

        if not cfg or not cfg.get("review_channel_id"):
            await interaction.response.send_message(
                "Verification isn't fully configured on this server yet. "
                "Please contact a staff member.",
                ephemeral=True,
            )
            return

        review_channel = guild.get_channel(cfg["review_channel_id"])
        if review_channel is None:
            await interaction.response.send_message(
                "The staff review channel could not be found. Please contact a staff member.",
                ephemeral=True,
            )
            return

        answers = {f"q{i}": field.value for i, field in enumerate(self.field_map)}
        application_id = await bot.db.create_application(guild.id, interaction.user.id, answers)
        application = await bot.db.get_application(application_id)

        review_view = ReviewView(application_id)
        embed = utils.build_review_embed(interaction.user, application, cfg["questions"])

        staff_role_id = cfg.get("staff_role_id")
        ping_content = None
        if staff_role_id:
            ping_content = f"🔔 <@&{staff_role_id}> — new application to review!"

        try:
            msg = await review_channel.send(
                content=ping_content,
                embed=embed,
                view=review_view,
                allowed_mentions=discord.AllowedMentions(roles=True, everyone=False, users=False),
            )
            await bot.db.set_application_message(application_id, msg.id)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to post in the staff review channel. "
                "Please contact a staff member.",
                ephemeral=True,
            )
            return

        try:
            await interaction.user.send(embed=utils.submitted_dm_embed())
        except discord.Forbidden:
            pass  # not fatal — the ephemeral reply below still confirms it

        await interaction.response.send_message(
            "🟡 Codsigaaga waa la gudbiyay! Staff-ku dib ayay u eegi doonaan.\n"
            "(Your application has been submitted — staff will review it shortly.)",
            ephemeral=True,
        )


class VerificationPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Apply",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="vxr:apply",
    )
    async def apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = interaction.client
        guild = interaction.guild
        cfg = await bot.db.get_guild_config(guild.id)

        if not cfg:
            await interaction.response.send_message(
                "Verification isn't configured on this server yet.", ephemeral=True
            )
            return

        member = interaction.user
        verified_role = guild.get_role(cfg["verified_role_id"]) if cfg.get("verified_role_id") else None
        if verified_role and verified_role in member.roles:
            await interaction.response.send_message("You're already verified! 🎉", ephemeral=True)
            return

        if await bot.db.has_pending_application(guild.id, member.id):
            await interaction.response.send_message(
                "You already have an application waiting for review. Please be patient — "
                "staff will get to it soon.",
                ephemeral=True,
            )
            return

        latest = await bot.db.get_latest_application(guild.id, member.id)
        cooldown_minutes = cfg.get("cooldown_minutes", config.DEFAULT_COOLDOWN_MINUTES)
        if latest and latest["status"] == "denied" and latest.get("reviewed_at") and cooldown_minutes > 0:
            reviewed_at = datetime.fromisoformat(latest["reviewed_at"])
            unlock_at = reviewed_at + timedelta(minutes=cooldown_minutes)
            now = datetime.now(timezone.utc)
            if now < unlock_at:
                ts = int(unlock_at.timestamp())
                await interaction.response.send_message(
                    f"Your last application was denied. You can re-apply <t:{ts}:R>.",
                    ephemeral=True,
                )
                return

        questions = cfg.get("questions") or config.DEFAULT_QUESTIONS
        await interaction.response.send_modal(VerificationModal(questions))


class DenyReasonModal(discord.ui.Modal, title="Deny Application"):
    reason = discord.ui.TextInput(
        label="Denial reason (sent to the applicant)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=300,
        placeholder="e.g. In-game name could not be verified.",
    )

    def __init__(self, application_id: int, message: discord.Message):
        super().__init__(timeout=300)
        self.application_id = application_id
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        guild = interaction.guild

        finalized = await bot.db.finalize_application(
            self.application_id, "denied", interaction.user.id, deny_reason=self.reason.value
        )
        if not finalized:
            await interaction.response.send_message(
                "⚠️ This application has already been processed by someone else.",
                ephemeral=True,
            )
            return

        application = await bot.db.get_application(self.application_id)
        member = guild.get_member(application["user_id"])

        await interaction.response.defer()

        if member is None:
            warnings = ["Member is no longer in the server — role/nickname changes skipped."]
        else:
            warnings = await utils.process_denial(
                bot, guild, member, interaction.user, self.reason.value, application
            )

        cfg = await bot.db.get_guild_config(guild.id)
        applicant_display = member if member else await bot.fetch_user(application["user_id"])
        embed = utils.build_review_embed(applicant_display, application, cfg["questions"])
        if warnings:
            embed.add_field(name="⚠️ Warnings", value="\n".join(warnings)[:1024], inline=False)

        await self.message.edit(embed=embed, view=None)


class ReviewView(discord.ui.View):
    def __init__(self, application_id: int):
        super().__init__(timeout=None)
        self.application_id = application_id
        self.accept_btn.custom_id = f"vxr:accept:{application_id}"
        self.deny_btn.custom_id = f"vxr:deny:{application_id}"

    @discord.ui.button(label="Accept", emoji="✅", style=discord.ButtonStyle.green)
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = interaction.client
        if not await utils.require_staff(bot, interaction):
            return

        guild = interaction.guild
        finalized = await bot.db.finalize_application(self.application_id, "accepted", interaction.user.id)
        if not finalized:
            await interaction.response.send_message(
                "⚠️ This application has already been processed by someone else.",
                ephemeral=True,
            )
            return

        application = await bot.db.get_application(self.application_id)
        member = guild.get_member(application["user_id"])

        await interaction.response.defer()

        if member is None:
            warnings = ["Member is no longer in the server — role/nickname changes skipped."]
            applicant_display = await bot.fetch_user(application["user_id"])
        else:
            warnings = await utils.process_acceptance(bot, guild, member, interaction.user, application)
            applicant_display = member

        cfg = await bot.db.get_guild_config(guild.id)
        embed = utils.build_review_embed(applicant_display, application, cfg["questions"])
        if warnings:
            embed.add_field(name="⚠️ Warnings", value="\n".join(warnings)[:1024], inline=False)

        await interaction.message.edit(embed=embed, view=None)

    @discord.ui.button(label="Deny", emoji="❌", style=discord.ButtonStyle.red)
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = interaction.client
        if not await utils.require_staff(bot, interaction):
            return

        application = await bot.db.get_application(self.application_id)
        if not application or application["status"] != "pending":
            await interaction.response.send_message(
                "⚠️ This application has already been processed.", ephemeral=True
            )
            return

        await interaction.response.send_modal(DenyReasonModal(self.application_id, interaction.message))


class VerificationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        cfg = await self.bot.db.get_guild_config(guild.id)
        if not cfg:
            return

        rejoin_policy = cfg.get("rejoin_policy", config.DEFAULT_REJOIN_POLICY)
        previously_verified = await self.bot.db.is_previously_verified(guild.id, member.id)

        if rejoin_policy == "permanent" and previously_verified:
            ok1, msg1 = await utils.safe_add_role(guild, member, cfg.get("verified_role_id"), "Rejoin — permanent verification")
            ok2, msg2 = await utils.safe_add_role(guild, member, cfg.get("member_role_id"), "Rejoin — permanent verification")
            nick_ok, nick_msg = await utils.apply_member_prefix(member)
            # Re-derive the staff/leadership prefix from their CURRENT roles
            # (not just the old flag) so a rejoining admin/leader gets the
            # correct prefix even if their rank changed while they were gone.
            staff_entry = utils.get_highest_staff_role(member)
            if staff_entry is not None:
                await utils.apply_configured_prefix(member)
                await self.bot.db.set_staff_prefix_flag(guild.id, member.id, True)
            elif await self.bot.db.has_staff_prefix(guild.id, member.id):
                await self.bot.db.set_staff_prefix_flag(guild.id, member.id, False)

            log_embed = discord.Embed(
                title="🔁 Returning Member — Verification Restored",
                color=config.COLOR_ACCEPTED,
            )
            log_embed.add_field(name="Member", value=f"{member.mention} (`{member.id}`)", inline=False)
            warnings = [m for ok, m in [(ok1, msg1), (ok2, msg2), (nick_ok, nick_msg)] if not ok]
            if warnings:
                log_embed.add_field(name="⚠️ Warnings", value="\n".join(warnings)[:1024], inline=False)
            await utils.send_log(self.bot, guild, log_embed)
            return

        # Default path: new or re-verifying member gets Unverified.
        ok, msg = await utils.safe_add_role(guild, member, cfg.get("unverified_role_id"), "New member — pending verification")
        if not ok:
            log.warning("Could not assign Unverified role in guild %s: %s", guild.id, msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(VerificationCog(bot))
