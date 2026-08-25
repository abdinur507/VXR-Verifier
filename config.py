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
