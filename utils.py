"""
Shared helpers used by every cog: permission checks, role-hierarchy safety,
nickname/prefix management, and common embed builders. Centralizing these
means /accept, the Accept button, and /verify all behave identically instead
of drifting apart.
"""

import logging
from datetime import datetime
from typing import Optional

import discord

import config

log = logging.getLogger("vxr-verifier")


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

async def is_staff(bot, interaction: discord.Interaction) -> bool:
    """Administrator OR holder of any configured staff role."""
    if interaction.user.guild_permissions.administrator:
        return True
    cfg = await bot.db.get_guild_config(interaction.guild.id)
    if not cfg or not cfg.get("staff_role_ids"):
        return False
    user_role_ids = {r.id for r in interaction.user.roles}
    return any(rid in user_role_ids for rid in cfg["staff_role_ids"])


async def require_staff(bot, interaction: discord.Interaction) -> bool:
    """Sends the standard denial message and returns False if not staff."""
    if await is_staff(bot, interaction):
        return True
    message = "❌ You do not have permission to review applications."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
    return False


# ---------------------------------------------------------------------------
# Role hierarchy safety
# ---------------------------------------------------------------------------

def bot_can_manage_role(guild: discord.Guild, role: Optional[discord.Role]) -> bool:
    if role is None:
        return False
    me = guild.me
    if me is None:
        return False
    if not me.guild_permissions.manage_roles:
        return False
    return me.top_role > role


def bot_can_manage_member(guild: discord.Guild, member: discord.Member) -> bool:
    me = guild.me
    if me is None or member is None:
        return False
    if member.id == guild.owner_id:
        return False
    return me.top_role > member.top_role


async def safe_add_role(guild: discord.Guild, member: discord.Member, role_id: Optional[int], reason: str) -> tuple[bool, str]:
    if not role_id:
        return False, "Role is not configured."
    role = guild.get_role(role_id)
    if role is None:
        return False, f"Configured role `{role_id}` no longer exists."
    if not bot_can_manage_role(guild, role):
        return False, (
            f"I can't manage the {role.mention} role — my top role must be positioned "
            "above it in Server Settings → Roles."
        )
    if role in member.roles:
        return True, "Already had role."
    try:
        await member.add_roles(role, reason=reason)
        return True, "OK"
    except discord.Forbidden:
        return False, "Missing permission to add that role."
    except discord.HTTPException as e:
        return False, f"Discord API error while adding role: {e}"


async def safe_remove_role(guild: discord.Guild, member: discord.Member, role_id: Optional[int], reason: str) -> tuple[bool, str]:
    if not role_id:
        return False, "Role is not configured."
    role = guild.get_role(role_id)
    if role is None:
        return False, f"Configured role `{role_id}` no longer exists."
    if role not in member.roles:
        return True, "Did not have role."
    if not bot_can_manage_role(guild, role):
        return False, (
            f"I can't manage the {role.mention} role — my top role must be positioned "
            "above it in Server Settings → Roles."
        )
    try:
        await member.remove_roles(role, reason=reason)
        return True, "OK"
    except discord.Forbidden:
        return False, "Missing permission to remove that role."
    except discord.HTTPException as e:
        return False, f"Discord API error while removing role: {e}"


# ---------------------------------------------------------------------------
# VXR nickname / prefix management
# ---------------------------------------------------------------------------

def strip_vxr_prefix(name: str) -> str:
    """Removes a leading VXR or VXR-Staff prefix if present, whitespace-safe."""
    for prefix in (config.VXR_STAFF_PREFIX, config.VXR_MEMBER_PREFIX):
        if name.startswith(prefix):
            return name[len(prefix):].strip()
    return name.strip()


def _utf16_length(s: str) -> int:
    """Discord validates nickname length the way JavaScript does: by UTF-16
    code units, not Unicode codepoints. The stylized 𝑽𝑿𝑹 characters used in
    the prefixes are in Unicode's supplementary plane, so each one is a
    surrogate PAIR — 2 units — even though Python's len() counts it as 1.
    Using len() here under-counts and lets nicknames through that Discord
    then rejects as too long, especially the staff prefix (it has more of
    these characters than the member prefix)."""
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in s)


def build_nickname(base_name: str, prefix: str) -> str:
    base = strip_vxr_prefix(base_name)
    prefix_units = _utf16_length(prefix)
    max_base_units = config.MAX_NICKNAME_LENGTH - prefix_units

    if max_base_units <= 0:
        # The prefix alone is already at/over Discord's limit — there's no
        # room for any name at all. Truncate the prefix itself as a last
        # resort rather than producing something Discord will reject outright.
        truncated = []
        units = 0
        for ch in prefix:
            w = 2 if ord(ch) > 0xFFFF else 1
            if units + w > config.MAX_NICKNAME_LENGTH:
                break
            truncated.append(ch)
            units += w
        return "".join(truncated)

    trimmed_chars = []
    units = 0
    for ch in base:
        w = 2 if ord(ch) > 0xFFFF else 1
        if units + w > max_base_units:
            break
        trimmed_chars.append(ch)
        units += w
    trimmed_base = "".join(trimmed_chars).rstrip()

    return f"{prefix}{trimmed_base}"


async def safe_set_nickname(member: discord.Member, new_nick: str, reason: str) -> tuple[bool, str]:
    guild = member.guild
    if member.id == guild.owner_id:
        return False, "Skipped: cannot change the server owner's nickname."
    me = guild.me
    if me is None or not me.guild_permissions.manage_nicknames:
        return False, "I'm missing the Manage Nicknames permission."
    if me.top_role <= member.top_role:
        return False, "My role must be above the member's top role to change their nickname."
    if member.display_name == new_nick:
        return True, "Nickname already correct."
    try:
        await member.edit(nick=new_nick, reason=reason)
        return True, "OK"
    except discord.Forbidden:
        return False, "Missing permission to change that member's nickname."
    except discord.HTTPException as e:
        return False, f"Discord API error while changing nickname: {e}"


def sanitize_ingame_name(name: str) -> str:
    """Cleans up a free-text application answer before it's used in a nickname
    (collapses newlines/extra whitespace from the modal field, trims edges)."""
    return " ".join(name.split())


async def apply_member_prefix(member: discord.Member, ingame_name: Optional[str] = None) -> tuple[bool, str]:
    base = sanitize_ingame_name(ingame_name) if ingame_name else ""
    if not base:
        base = member.display_name  # fallback: no in-game name on file (e.g. /verify with no application)
    new_nick = build_nickname(base, config.VXR_MEMBER_PREFIX)
    return await safe_set_nickname(member, new_nick, "Verification accepted — applying VXR prefix with in-game name")


async def apply_staff_prefix(member: discord.Member) -> tuple[bool, str]:
    new_nick = build_nickname(member.display_name, config.VXR_STAFF_PREFIX)
    return await safe_set_nickname(member, new_nick, "Staff VXR prefix applied")


async def clear_vxr_prefix(member: discord.Member) -> tuple[bool, str]:
    base = strip_vxr_prefix(member.display_name)
    return await safe_set_nickname(member, base, "VXR prefix removed")


# ---------------------------------------------------------------------------
# Embeds
# ---------------------------------------------------------------------------

def format_app_id(application_id: int) -> str:
    return f"APP-{application_id:06d}"


def status_color(status: str) -> int:
    return {
        "pending": config.COLOR_PENDING,
        "accepted": config.COLOR_ACCEPTED,
        "denied": config.COLOR_DENIED,
    }.get(status, config.COLOR_INFO)


def build_review_embed(
    applicant: discord.abc.User,
    application: dict,
    questions: list[str],
) -> discord.Embed:
    status = application["status"]
    embed = discord.Embed(
        title=f"{config.STATUS_EMOJI.get(status, '')} Verification Application {format_app_id(application['id'])}",
        color=status_color(status),
    )
    embed.set_thumbnail(url=applicant.display_avatar.url)
    embed.add_field(name="🧑 Applicant", value=applicant.mention, inline=True)
    embed.add_field(name="🆔 Discord ID", value=f"`{applicant.id}`", inline=True)
    embed.add_field(name="🟡 Status", value=f"{config.STATUS_EMOJI.get(status,'')} {status.capitalize()}", inline=True)

    answers = application["answers"]
    for i, q in enumerate(questions):
        key = f"q{i}"
        value = answers.get(key, "-")
        label = "🎮 In-game name" if i == 0 else q
        embed.add_field(name=label, value=value[:1024] if value else "-", inline=False)

    submitted = application.get("submitted_at")
    if submitted:
        try:
            ts = int(datetime.fromisoformat(submitted).timestamp())
            embed.add_field(name="📅 Submitted", value=f"<t:{ts}:F>", inline=False)
        except ValueError:
            pass

    if application.get("reviewer_id"):
        embed.add_field(name="👮 Reviewer", value=f"<@{application['reviewer_id']}>", inline=True)
    if application.get("reviewed_at"):
        try:
            ts = int(datetime.fromisoformat(application["reviewed_at"]).timestamp())
            embed.add_field(name="🕒 Reviewed", value=f"<t:{ts}:F>", inline=True)
        except ValueError:
            pass
    if application.get("deny_reason"):
        embed.add_field(name="❌ Denial reason", value=application["deny_reason"][:1024], inline=False)

    embed.set_footer(text="JAMAAHIRTA GANG 『𝑽𝑿𝑹』 • Verification System")
    return embed


def submitted_dm_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🟡 Application Submitted",
        description=(
            "Codsigaaga waa la gudbiyay waxaana loo diray Staff-ka si ay u dib u eegaan.\n\n"
            "Fadlan sug inta codsigaaga la baarayo."
        ),
        color=config.COLOR_PENDING,
    )
    return embed


def accepted_dm_embed(member: discord.abc.User) -> discord.Embed:
    embed = discord.Embed(
        title="🟢 Application Accepted",
        description=(
            f"Hambalyo **{member.display_name}**!\n\n"
            "Codsigaaga waa la aqbalay.\n\n"
            "Ku soo dhawoow **JAMAAHIRTA GANG 『𝑽𝑿𝑹』**! 🏴"
        ),
        color=config.COLOR_ACCEPTED,
    )
    return embed


def denied_dm_embed(reason: str) -> discord.Embed:
    embed = discord.Embed(
        title="🔴 Application Denied",
        description=(
            "Codsigaaga lama aqbalin.\n\n"
            f"**Sababta:** {reason}\n\n"
            "Waxaad dib u codsan kartaa marka aad buuxiso shuruudaha."
        ),
        color=config.COLOR_DENIED,
    )
    return embed


# ---------------------------------------------------------------------------
# Logging to the configured log channel
# ---------------------------------------------------------------------------

async def send_log(bot, guild: discord.Guild, embed: discord.Embed):
    cfg = await bot.db.get_guild_config(guild.id)
    if not cfg or not cfg.get("log_channel_id"):
        return
    channel = guild.get_channel(cfg["log_channel_id"])
    if channel is None:
        log.warning("Log channel %s not found in guild %s", cfg["log_channel_id"], guild.id)
        return
    try:
        await channel.send(embed=embed)
    except discord.HTTPException as e:
        log.error("Failed to send log message in guild %s: %s", guild.id, e)


# ---------------------------------------------------------------------------
# Centralized accept / deny processing — used by BOTH the review buttons and
# the manual /accept /deny /verify /unverify commands, so behaviour never
# drifts between the two entry points.
# ---------------------------------------------------------------------------

async def process_acceptance(
    bot,
    guild: discord.Guild,
    member: discord.Member,
    reviewer: discord.abc.User,
    application: Optional[dict] = None,
) -> list[str]:
    """Runs the full acceptance flow. Returns a list of non-fatal warning strings."""
    cfg = await bot.db.get_guild_config(guild.id)
    warnings: list[str] = []

    ok, msg = await safe_remove_role(guild, member, cfg.get("unverified_role_id"), "Verification accepted")
    if not ok:
        warnings.append(f"Unverified role: {msg}")

    ok, msg = await safe_add_role(guild, member, cfg.get("verified_role_id"), "Verification accepted")
    if not ok:
        warnings.append(f"Verified role: {msg}")

    ok, msg = await safe_add_role(guild, member, cfg.get("member_role_id"), "Verification accepted")
    if not ok:
        warnings.append(f"Member role: {msg}")

    ingame_name = None
    if application and application.get("answers"):
        ingame_name = application["answers"].get("q0")  # q0 is always the in-game-name question by convention

    nick_ok, nick_msg = await apply_member_prefix(member, ingame_name=ingame_name)
    if not nick_ok:
        warnings.append(f"Nickname: {nick_msg}")

    await bot.db.mark_verified(guild.id, member.id)

    dm_sent = True
    try:
        await member.send(embed=accepted_dm_embed(member))
    except discord.Forbidden:
        dm_sent = False
        warnings.append("Could not DM the applicant (their DMs are closed).")
    except discord.HTTPException as e:
        dm_sent = False
        warnings.append(f"Could not DM the applicant: {e}")

    log_embed = discord.Embed(
        title=f"🟢 Application Accepted {format_app_id(application['id']) if application else ''}",
        color=config.COLOR_ACCEPTED,
    )
    log_embed.add_field(name="Applicant", value=f"{member.mention} (`{member.id}`)", inline=False)
    log_embed.add_field(name="Reviewer", value=reviewer.mention, inline=True)
    log_embed.add_field(name="DM sent", value="Yes" if dm_sent else "No", inline=True)
    if warnings:
        log_embed.add_field(name="⚠️ Warnings", value="\n".join(warnings)[:1024], inline=False)
    await send_log(bot, guild, log_embed)

    return warnings


async def process_denial(
    bot,
    guild: discord.Guild,
    member: discord.Member,
    reviewer: discord.abc.User,
    reason: str,
    application: Optional[dict] = None,
) -> list[str]:
    warnings: list[str] = []

    dm_sent = True
    try:
        await member.send(embed=denied_dm_embed(reason))
    except discord.Forbidden:
        dm_sent = False
        warnings.append("Could not DM the applicant (their DMs are closed).")
    except discord.HTTPException as e:
        dm_sent = False
        warnings.append(f"Could not DM the applicant: {e}")

    log_embed = discord.Embed(
        title=f"🔴 Application Denied {format_app_id(application['id']) if application else ''}",
        color=config.COLOR_DENIED,
    )
    log_embed.add_field(name="Applicant", value=f"{member.mention} (`{member.id}`)", inline=False)
    log_embed.add_field(name="Reviewer", value=reviewer.mention, inline=True)
    log_embed.add_field(name="DM sent", value="Yes" if dm_sent else "No", inline=True)
    log_embed.add_field(name="Reason", value=reason[:1024], inline=False)
    await send_log(bot, guild, log_embed)

    return warnings


async def process_unverify(bot, guild: discord.Guild, member: discord.Member, moderator: discord.abc.User) -> list[str]:
    cfg = await bot.db.get_guild_config(guild.id)
    warnings: list[str] = []

    ok, msg = await safe_remove_role(guild, member, cfg.get("verified_role_id"), "Unverified by staff")
    if not ok:
        warnings.append(f"Verified role: {msg}")
    ok, msg = await safe_remove_role(guild, member, cfg.get("member_role_id"), "Unverified by staff")
    if not ok:
        warnings.append(f"Member role: {msg}")
    ok, msg = await safe_add_role(guild, member, cfg.get("unverified_role_id"), "Unverified by staff")
    if not ok:
        warnings.append(f"Unverified role: {msg}")

    nick_ok, nick_msg = await clear_vxr_prefix(member)
    if not nick_ok:
        warnings.append(f"Nickname: {nick_msg}")

    await bot.db.unmark_verified(guild.id, member.id)
    await bot.db.set_staff_prefix_flag(guild.id, member.id, False)

    log_embed = discord.Embed(title="🔒 Member Unverified", color=config.COLOR_INFO)
    log_embed.add_field(name="Member", value=f"{member.mention} (`{member.id}`)", inline=False)
    log_embed.add_field(name="Moderator", value=moderator.mention, inline=True)
    if warnings:
        log_embed.add_field(name="⚠️ Warnings", value="\n".join(warnings)[:1024], inline=False)
    await send_log(bot, guild, log_embed)

    return warnings