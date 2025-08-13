from __future__ import annotations
import os
import hikari
import lightbulb

TOKEN_PATH = "./statline/secrets/token"

try:
    with open(TOKEN_PATH, "r", encoding="utf-8") as f:
        token = f.read().strip()
except FileNotFoundError:
    raise RuntimeError(f"Discord token file not found at {TOKEN_PATH}")

if not token:
    raise RuntimeError("Discord token file is empty")

bot = hikari.GatewayBot(token=token)
client = lightbulb.client_from_app(bot)

@bot.listen(hikari.StartingEvent)
async def on_starting(_: hikari.StartingEvent) -> None:
    # Load any extensions
    # await client.load_extensions_from_package("./statline/discord/extensions")
    # Start the bot - make sure commands are synced properly
    await client.start()

bot.run()