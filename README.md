# 🔐 VXR Verifier

A complete, working Discord verification bot built for **JAMAAHIRTA GANG 『𝑽𝑿𝑹』**.

Every button, modal, slash command, role change, nickname change, DM, and log
in this project is real and functional — nothing here is a placeholder.

## What it does

- New members are automatically given the **Unverified** role and can only
  see the verification channel (you control this with normal Discord channel
  permissions, or your own overwrites — the bot handles the role side).
- A Somali-language verification panel with an **✅ Apply** button lives in
  the verification channel.
- Clicking Apply opens a modal with your configured application question(s)
  (in-game name by default — add more any time with `/setupverification`,
  no code changes needed).
- Submitted applications are posted as an embed with **✅ Accept** /
  **❌ Deny** buttons in your private staff review channel.
- **Accept** → removes Unverified, adds Verified + Member, applies the
  `『𝑽𝑿𝑹』 {name}` nickname prefix, DMs the applicant, logs the action.
- **Deny** → opens a modal asking for a reason, keeps the member Unverified,
  DMs them the reason, logs the action, and lets them re-apply after the
  configured cooldown.
- Buttons disable themselves the instant an application is processed, and a
  second click (or a race between two staff members) is rejected atomically
  at the database layer — an application can never be processed twice.
- Staff get a distinct `『𝑽𝑿𝑹・𝑺𝒕𝒂𝒇𝒇』 {name}` nickname prefix via
  `/staffprefix`, reversible with `/removestaffprefix`. Prefixes are never
  duplicated or stacked.
- Returning members are handled per your **rejoin policy**: either
  automatically restored to Verified + Member (default), or sent back
  through Unverified to re-apply.
- Everything is stored in SQLite (`data/verification.db`) and survives
  restarts — configuration, every application (with full answers, reviewer,
  timestamps, denial reasons), and verification history.

## Project structure

```
VXR-Verifier/
├── bot.py                 # entry point
├── config.py               # constants & defaults (no secrets)
├── database.py              # async SQLite layer
├── utils.py                  # permissions, role/nickname safety, embeds, shared accept/deny logic
├── requirements.txt
├── .env.example
├── README.md
├── cogs/
│   ├── verification.py     # panel, modal, on_member_join, Accept/Deny buttons
│   ├── applications.py      # /applications /application /accept /deny
│   ├── moderation.py         # /verify /unverify /verificationlogs
│   ├── prefixes.py            # /staffprefix /removestaffprefix
│   └── admin.py                # /setupverification /verification
└── data/
    └── verification.db     # created automatically on first run
```

## 1. Discord Developer Portal setup

1. Go to https://discord.com/developers/applications and create a new
   application, then add a Bot to it.
2. Under **Bot → Privileged Gateway Intents**, enable **Server Members
   Intent**. This is required for auto-role on join and rejoin handling.
3. Copy the bot token (**Bot → Reset Token**) — you'll need it for `.env`.
4. Under **OAuth2 → URL Generator**, select scopes `bot` and
   `applications.commands`, and these bot permissions at minimum:
   - Manage Roles
   - Manage Nicknames
   - View Channels / Send Messages / Embed Links
   - Read Message History
   Use the generated URL to invite the bot to your server.

**Important — role hierarchy:** in *Server Settings → Roles*, drag the
bot's own role **above** Unverified, Verified, Member, and the Staff role.
Discord bots can only add/remove/manage roles positioned below their own
highest role — the bot detects this and will tell you clearly if it can't
manage a role instead of failing silently.

## 2. Install & configure

```bash
git clone <this project>  # or just unzip it
cd VXR-Verifier
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:

```env
DISCORD_TOKEN=your-bot-token-here
GUILD_ID=your-server-id-here   # optional but recommended during setup — instant command sync
```

Run it:

```bash
python bot.py
```

You should see `Logged in as ... / Synced N command(s)` in the console.

## 3. In-Discord setup

Run once, as a server administrator:

```
/setupverification
```

All options are optional — anything you leave blank falls back to the
default JAMAAHIRTA GANG『𝑽𝑿𝑹』role/channel IDs on first run, or to your
previous setting if you run the command again to change just one thing.
You can configure:

- `verification_channel`, `review_channel`, `log_channel`
- `unverified_role`, `verified_role`, `member_role`, `staff_role`
- `cooldown_minutes` (reapply cooldown after a denial)
- `rejoin_policy`: **Permanent verification** (default) or **Require
  re-verification**
- `question_1` … `question_5` (up to 5 application questions — Discord's
  modal limit)

Then post the panel:

```
/verification
```

This sends the Somali verification embed with the ✅ Apply button to your
configured verification channel.

## 4. Commands reference

| Command | Who | What it does |
|---|---|---|
| `/setupverification` | Admin | Configure channels, roles, questions, cooldown, rejoin policy |
| `/verification` | Admin | (Re)send the verification panel |
| `/applications` | Staff | List pending applications |
| `/application <id>` | Staff | View one application in full |
| `/accept <user>` | Staff | Manually approve a member |
| `/deny <user> <reason>` | Staff | Manually deny a member |
| `/verify <user>` | Staff | Directly verify a member, no application needed |
| `/unverify <user>` | Staff | Strip verification, return to Unverified |
| `/verificationlogs` | Staff | Stats: pending/accepted/denied counts, config summary |
| `/staffprefix <user>` | Staff | Apply the `『𝑽𝑿𝑹・𝑺𝒕𝒂𝒇𝒇』` nickname prefix |
| `/removestaffprefix <user>` | Staff | Remove it, restore the normal `『𝑽𝑿𝑹』` prefix |

"Staff" = server Administrators, or anyone holding the role set as
`staff_role` in `/setupverification`. Unauthorized users clicking Accept/Deny
get: *"❌ You do not have permission to review applications."*

## 5. How data is stored

SQLite database at `data/verification.db`, three tables:

- **guild_config** — one row per server: channels, roles, questions (JSON),
  cooldown, rejoin policy.
- **applications** — one row per submitted or manually-created application:
  answers (JSON), status, reviewer, submission/review timestamps, denial
  reason, the Discord message ID of its review embed.
- **verified_members** — tracks who has ever been verified per guild (for
  the rejoin policy) and whether they currently hold the staff nickname
  prefix.

Back this file up like any database if you care about history — it is the
single source of truth and is never rebuilt from Discord state.

## 6. Reliability notes

- All persistent buttons (`Apply`, `Accept`, `Deny`) use fixed `custom_id`s
  and are re-registered on every startup by reading pending applications
  back out of the database — they keep working after a restart or a crash,
  with no manual re-posting needed.
- Accepting/denying is guarded by a single atomic SQL `UPDATE ... WHERE
  status = 'pending'`; if two staff click at once, only the first succeeds
  and the second gets *"already been processed"*.
- Role and nickname changes never crash the bot: every call is wrapped and
  checked against role hierarchy and the `Manage Roles` / `Manage
  Nicknames` permissions first. Failures are reported back to whoever ran
  the action and written to the log channel instead of failing silently.
- The server owner's nickname is never touched (Discord doesn't allow bots
  to change it anyway).
- Nicknames longer than Discord's 32-character limit are trimmed from the
  *name*, never the `『𝑽𝑿𝑹』` / `『𝑽𝑿𝑹・𝑺𝒕𝒂𝒇𝒇』` prefix, and prefixes are
  stripped before a new one is applied so you never get double-prefixed
  nicknames.
- discord.py's gateway client reconnects automatically on connection loss;
  no extra code is needed for that.
- DMs that fail (closed DMs) are caught and reported as a warning rather
  than raising an error — the role/verification action still completes.

## 7. Hosting

This runs anywhere Python 3.10+ can run persistently: Railway, Fly.io,
a VPS with `systemd`/`pm2`/`screen`, Replit with an always-on plan, etc.
The only requirements are outbound internet access and a writable `data/`
folder for the SQLite file. No inbound ports are needed.

## 8. Extending

- **More questions:** re-run `/setupverification` with more `question_N`
  values — nothing else needs to change.
- **Different servers:** all configuration is per-guild in the database, so
  the same bot process can serve multiple servers with independent setups.
- **Different wording:** the Somali panel text and DM templates live in
  `cogs/verification.py` (`SOMALI_PANEL_TEXT`) and `utils.py`
  (`accepted_dm_embed`, `denied_dm_embed`, `submitted_dm_embed`).
