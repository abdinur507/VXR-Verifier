"""
VXR Verifier — entry point.

Run with:  python bot.py
Requires:  DISCORD_TOKEN in .env (see .env.example)
"""

import logging
import sys

import discord
from discord.ext import commands

import config  # noqa: F401  (importing this loads .env — see config.py)
from database import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
# Make sure nothing ever accidentally logs the token.
logging.getLogger("discord.http").setLevel(logging.WARNING)

log = logging.getLogger("vxr-verifier")

INTENTS = discord.Intents.default()
INTENTS.members = True  # required for on_member_join auto-role / rejoin handling

EXTENSIONS = (
    "cogs.verification",
    "cogs.applications",
    "cogs.moderation",
    "cogs.prefixes",
    "cogs.admin",
    "cogs.staffroles",
    "cogs.health",
)


class VXRVerifier(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="vxr!unused-", intents=INTENTS, help_command=None)
        self.db = Database(config.DB_PATH)

    async def setup_hook(self):
        await self.db.connect()
        log.info("Database connected at %s", config.DB_PATH)

        for ext in EXTENSIONS:
            await self.load_extension(ext)
            log.info("Loaded extension: %s", ext)

        # Re-register persistent views so every button keeps working across restarts.
        from cogs.verification import VerificationPanelView, ReviewView

        self.add_view(VerificationPanelView())

        # One ReviewView per still-pending application, across every guild the bot is in.
        cur = await self.db._conn.execute(  # internal use: startup-only bulk read
            "SELECT id FROM applications WHERE status = 'pending'"
        )
        rows = await cur.fetchall()
        for row in rows:
            self.add_view(ReviewView(row["id"]))
        log.info("Re-registered %d pending application review view(s).", len(rows))

        if config.GUILD_ID:
            guild_obj = discord.Object(id=int(config.GUILD_ID))

            # Copy the in-memory global commands to the guild FIRST, sync
            # them there, and only THEN wipe the global copy from Discord.
            # (Clearing before copying would copy nothing, and leaving the
            # global copy in place is what causes commands to show twice.)
            self.tree.copy_global_to(guild=guild_obj)
            synced = await self.tree.sync(guild=guild_obj)
            log.info("Synced %d command(s) to guild %s (fast dev sync).", len(synced), config.GUILD_ID)

            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            log.info("Cleared global commands so they can't duplicate the guild-scoped ones.")
        else:
            synced = await self.tree.sync()
            log.info("Synced %d command(s) globally.", len(synced))

    async def close(self):
        await self.db.close()
        await super().close()


bot = VXRVerifier()


@bot.event
async def on_ready():
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    log.info("Serving %d guild(s).", len(bot.guilds))
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="for new members 🔐"))


@bot.event
async def on_disconnect():
    log.warning("Disconnected from Discord — discord.py will automatically attempt to reconnect.")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    """Catch-all so a bad command never crashes the bot or leaves the user hanging."""
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        message = f"Slow down — try again in {error.retry_after:.1f}s."
    elif isinstance(error, discord.app_commands.MissingPermissions):
        message = "❌ You don't have permission to do that."
    else:
        log.exception("Unhandled application command error", exc_info=error)
        message = "❌ Something went wrong handling that command. The error has been logged."

    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


if __name__ == "__main__":
    if not config.DISCORD_TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Copy .env.example to .env and add your bot token.")
    bot.run(config.DISCORD_TOKEN, log_handler=None)
