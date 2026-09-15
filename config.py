"""
Central place for constants and default values.

These defaults are only used to PRE-FILL the /setupverification command and
as a one-time fallback for brand-new guilds. Everything a guild actually
uses at runtime is read from the SQLite database (see database.py), never
from hard-coded values scattered through the code.
"""

import os

from dotenv import load_dotenv

# Load .env here, at the top of the very first module anything else imports,
# so DISCORD_TOKEN is guaranteed to be populated before config.py reads it
# below — regardless of what order bot.py imports things in.
load_dotenv()

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # optional: speeds up slash command sync during dev

# ---------------------------------------------------------------------------
# Bot identity
# ---------------------------------------------------------------------------
BOT_NAME = "🔐 𝑽𝑿𝑹 𝑽𝒆𝒓𝒊𝒇𝒊𝒆𝒓"

# ---------------------------------------------------------------------------
# Initial configuration values (from the JAMAAHIRTA GANG『𝑽𝑿𝑹』setup brief).
# These are ONLY used as defaults inside /setupverification — an admin can
# override every one of them, and after that the database is authoritative.
# ---------------------------------------------------------------------------
DEFAULT_UNVERIFIED_ROLE_ID = 1541466086388670494
DEFAULT_VERIFIED_ROLE_ID = 1541433664733323304
DEFAULT_MEMBER_ROLE_ID = 1541432865970069525
DEFAULT_REVIEW_CHANNEL_ID = 1541459843796181032
DEFAULT_LOG_CHANNEL_ID = 1541459843796181032

DEFAULT_QUESTIONS = ["Waa maxay magaca game-ka aad ku dheesho?"]
DEFAULT_COOLDOWN_MINUTES = 60
DEFAULT_REJOIN_POLICY = "permanent"  # "permanent" or "reverify"

MAX_QUESTIONS = 5  # hard Discord modal limit

# ---------------------------------------------------------------------------
# Nickname prefixes
# ---------------------------------------------------------------------------
VXR_MEMBER_PREFIX = "『𝑽𝑿𝑹』 "
VXR_STAFF_PREFIX = "『𝑽𝑿𝑹・𝑺𝒕𝒂𝒇𝒇』 "
MAX_NICKNAME_LENGTH = 32  # Discord hard limit

# ---------------------------------------------------------------------------
# Leadership & staff role hierarchy
#
# One centralized table drives THREE things at once:
#   1. who is allowed to review/accept/deny applications ("permission system"),
#   2. which nickname prefix a member gets, and
#   3. which prefix wins when a member holds more than one of these roles
#      (lower "priority" number = higher rank = wins).
#
# Leadership roles get their own distinct prefixes. The existing staff roles
# (Guddiga → Ticket Helper) keep using VXR_STAFF_PREFIX exactly as before —
# nothing about their look changes, only that they're now driven from this
# same table instead of a single flat "staff_role_id".
#
# Do not change these role IDs without updating them on the Discord server
# first — a stale/incorrect ID here just means that role is silently ignored.
# ---------------------------------------------------------------------------
STAFF_ROLE_TABLE = {
    # --- Leadership: distinct prefixes ---
    1541426955768045639: {"name": "Owner",        "priority": 1,  "prefix": "『𝑶𝑾』 ",  "review": True, "accept": True, "deny": True, "manual_verify": True},
    1541427794859397260: {"name": "Co-Owner",     "priority": 2,  "prefix": "『𝑪𝑶』 ",      "review": True, "accept": True, "deny": True, "manual_verify": True},
    1541427225335697428: {"name": "Boss",         "priority": 3,  "prefix": "『𝑩𝑶𝑺𝑺』 ",    "review": True, "accept": True, "deny": True, "manual_verify": True},
    1541924412566016010: {"name": "Underboss I",  "priority": 4,  "prefix": "『𝑼𝑩 𝑰』 ",    "review": True, "accept": True, "deny": True, "manual_verify": True},
    1543887900184154135: {"name": "Underboss II", "priority": 5,  "prefix": "『𝑼𝑩 𝑰𝑰』 ",   "review": True, "accept": True, "deny": True, "manual_verify": True},
    # --- Staff: existing VXR staff prefix, preserved exactly ---
    1543917451119562852: {"name": "Guddiga",       "priority": 6,  "prefix": VXR_STAFF_PREFIX, "review": True, "accept": True, "deny": True, "manual_verify": True},
    1541427866003046412: {"name": "Head of Staff", "priority": 7,  "prefix": VXR_STAFF_PREFIX, "review": True, "accept": True, "deny": True, "manual_verify": True},
    1543899338458275911: {"name": "Admin",         "priority": 8,  "prefix": VXR_STAFF_PREFIX, "review": True, "accept": True, "deny": True, "manual_verify": True},
    1541428977581690920: {"name": "Moderator",     "priority": 9,  "prefix": VXR_STAFF_PREFIX, "review": True, "accept": True, "deny": True, "manual_verify": False},
    1541435655576363078: {"name": "Staff",         "priority": 10, "prefix": VXR_STAFF_PREFIX, "review": True, "accept": True, "deny": True, "manual_verify": False},
    1541431655938523166: {"name": "Stage Mod",     "priority": 11, "prefix": VXR_STAFF_PREFIX, "review": True, "accept": False, "deny": False, "manual_verify": False},
    1541429479971233842: {"name": "Ticket Helper", "priority": 12, "prefix": VXR_STAFF_PREFIX, "review": True, "accept": False, "deny": False, "manual_verify": False},
}

# ---------------------------------------------------------------------------
# Colors / emojis
# ---------------------------------------------------------------------------
COLOR_PENDING = 0xF1C40F
COLOR_ACCEPTED = 0x2ECC71
COLOR_DENIED = 0xE74C3C
COLOR_INFO = 0x5865F2

STATUS_EMOJI = {
    "pending": "🟡",
    "accepted": "🟢",
    "denied": "🔴",
}

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "verification.db")
