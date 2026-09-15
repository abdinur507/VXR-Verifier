"""
/health - one-shot diagnostic snapshot: latency, database connectivity,
guild/channel/role configuration, bot permissions, role-hierarchy warnings,
command sync status, and persistent-view status.
"""

import time

import discord
from discord import app_commands
from discord.ext import commands

import config
import utils


class HealthCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="health", description="Show a full bot health/diagnostics report")
    async def health(self, interaction: discord.Interaction):
        if not await utils.require_staff(self.bot, interaction):
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        me = guild.me

        # --- Database ---
        db_ok = True
        db_error = ""
        t0 = time.monotonic()
        try:
            await self.bot.db.get_guild_config(guild.id)
        except Exception as e:  # noqa: BLE001 — this is a diagnostic probe, any failure counts
            db_ok = False
            db_error = str(e)
        db_ms = (time.monotonic() - t0) * 1000

        cfg = await self.bot.db.get_guild_config(guild.id)

        # --- Channels ---
        def channel_status(cid, label):
            if not cid:
                return f"⚠️ {label}: not configured"
            ch = guild.get_channel(cid)
            return f"✅ {label}: {ch.mention}" if ch else f"❌ {label}: `{cid}` not found"

        channel_lines = [
            channel_status(cfg.get("verification_channel_id") if cfg else None, "Verification"),
            channel_status(cfg.get("review_channel_id") if cfg else None, "Review"),
            channel_status(cfg.get("log_channel_id") if cfg else None, "Log"),
        ] if cfg else ["⚠️ No guild configuration found — run `/setupverification`."]

        # --- Core roles ---
        def role_status(rid, label):
            if not rid:
                return f"⚠️ {label}: not configured"
            r = guild.get_role(rid)
            return f"✅ {label}: {r.mention}" if r else f"❌ {label}: `{rid}` not found"

        core_role_lines = [
            role_status(cfg.get("unverified_role_id") if cfg else None, "Unverified"),
            role_status(cfg.get("verified_role_id") if cfg else None, "Verified"),
            role_status(cfg.get("member_role_id") if cfg else None, "Member"),
            role_status(cfg.get("staff_role_id") if cfg else None, "Legacy staff"),
        ] if cfg else []

        # --- Leadership/staff table + hierarchy warnings ---
        hierarchy_warnings = []
        found, missing = 0, 0
        for role_id, entry in config.STAFF_ROLE_TABLE.items():
            role = guild.get_role(role_id)
            if role is None:
                missing += 1
                continue
            found += 1
            if me.top_role <= role:
                hierarchy_warnings.append(f"`{entry['name']}` ({role.mention}) is at/above my top role")

        # --- Permissions ---
        perms = me.guild_permissions
        perm_lines = [
            f"{'✅' if perms.manage_nicknames else '❌'} Manage Nicknames",
            f"{'✅' if perms.manage_roles else '❌'} Manage Roles",
            f"{'✅' if perms.send_messages else '❌'} Send Messages",
            f"{'✅' if perms.embed_links else '❌'} Embed Links",
            f"{'✅' if perms.view_channel else '❌'} View Channels",
        ]

        # --- Command sync / persistent views ---
        if config.GUILD_ID:
            app_cmd_count = len(self.bot.tree.get_commands(guild=discord.Object(id=int(config.GUILD_ID))))
        else:
            app_cmd_count = len(self.bot.tree.get_commands())
        pending_apps = await self.bot.db.list_pending_applications(guild.id, limit=1000)

        embed = discord.Embed(
            title="🩺 VXR Verifier — Health Report",
            color=config.COLOR_ACCEPTED if db_ok and not hierarchy_warnings else config.COLOR_PENDING,
        )
        embed.add_field(name="🏓 Latency", value=f"{self.bot.latency * 1000:.0f} ms", inline=True)
        embed.add_field(name="🗄️ Database", value=(f"✅ OK ({db_ms:.1f} ms)" if db_ok else f"❌ {db_error}"), inline=True)
        embed.add_field(name="🌐 Guild", value=f"✅ {guild.name} (`{guild.id}`)", inline=True)

        embed.add_field(name="📺 Channels", value="\n".join(channel_lines)[:1024], inline=False)
        if core_role_lines:
            embed.add_field(name="🎭 Core roles", value="\n".join(core_role_lines)[:1024], inline=False)

        embed.add_field(
            name="👑 Leadership/staff roles",
            value=f"{found} found in this server, {missing} not found",
            inline=True,
        )
        embed.add_field(name="🔝 My highest role", value=f"{me.top_role.mention} (pos {me.top_role.position})", inline=True)
        embed.add_field(name="🔐 Permissions", value="\n".join(perm_lines), inline=False)

        if hierarchy_warnings:
            embed.add_field(
                name="⚠️ Role hierarchy warnings",
                value=(
                    "\n".join(hierarchy_warnings[:10])[:1024]
                    + "\n\nMove my top role above these in Server Settings → Roles to manage them."
                ),
                inline=False,
            )
        else:
            embed.add_field(
                name="⚠️ Role hierarchy warnings",
                value="✅ None — I can manage every configured role found.",
                inline=False,
            )

        embed.add_field(name="📡 Commands registered", value=str(app_cmd_count), inline=True)
        embed.add_field(
            name="🔘 Persistent views",
            value=f"Panel: active\nPending-application buttons: {len(pending_apps)}",
            inline=True,
        )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(HealthCog(bot))
