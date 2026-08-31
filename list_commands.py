"""One-off: prints every command currently registered with Discord,
both global and guild-specific, so you can see the real state
(not what your Discord client has cached)."""
import asyncio
import discord
from discord.ext import commands
import config

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print("\n=== GLOBAL commands ===")
    global_cmds = await bot.tree.fetch_commands()
    for c in global_cmds:
        print(f"  {c.name}  (id={c.id})")
    print(f"  Total global: {len(global_cmds)}")

    if config.GUILD_ID:
        guild_obj = discord.Object(id=int(config.GUILD_ID))
        print(f"\n=== GUILD {config.GUILD_ID} commands ===")
        guild_cmds = await bot.tree.fetch_commands(guild=guild_obj)
        for c in guild_cmds:
            print(f"  {c.name}  (id={c.id})")
        print(f"  Total guild: {len(guild_cmds)}")

    await bot.close()

asyncio.run(bot.start(config.DISCORD_TOKEN))
