from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
from collections import defaultdict
from pathlib import Path

import aiohttp
import discord
from discord import app_commands
from dotenv import load_dotenv

from .music import AudioResolver, MusicError, parse_query
from .player import Player
from .spotify import Spotify

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
log = logging.getLogger(__name__)


class MusicBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none())
        self.tree = app_commands.CommandTree(self)
        self.players: dict[int, Player] = {}
        self.locks = defaultdict(asyncio.Lock)
        self.resolver = AudioResolver()
        self.ffmpeg = os.getenv("FFMPEG_PATH", "ffmpeg")

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self.spotify = Spotify(self.http_session, os.getenv("SPOTIFY_CLIENT_ID", ""), os.getenv("SPOTIFY_CLIENT_SECRET", ""))
        guild_id = os.getenv("DISCORD_GUILD_ID", "")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        log.info("Bot połączony z Discordem. Komendy są zarejestrowane.")

    async def close(self):
        for player in list(self.players.values()):
            await player.close()
        if hasattr(self, "http_session"):
            await self.http_session.close()
        await super().close()


bot = MusicBot()


def member_channel(interaction: discord.Interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        raise MusicError("Użyj tej komendy na serwerze Discord.")
    state = interaction.user.voice
    if not state or not state.channel:
        raise MusicError("Najpierw dołącz do zwykłego kanału głosowego.")
    if isinstance(state.channel, discord.StageChannel):
        raise MusicError("Na razie obsługuję zwykłe kanały głosowe, bez Stage.")
    return state.channel


def active_player(interaction):
    channel = member_channel(interaction)
    player = bot.players.get(interaction.guild_id)
    if not player or not player.voice.is_connected():
        raise MusicError("Nie odtwarzam teraz muzyki. Dodaj utwór przez /play.")
    if player.voice.channel.id != channel.id:
        raise MusicError("Dołącz do kanału głosowego, na którym jest bot.")
    return player


@bot.tree.command(name="play", description="Dodaj utwór lub publiczną playlistę Spotify / YouTube")
@app_commands.guild_only()
@app_commands.describe(query="Link do publicznej playlisty, utworu lub nazwa nagrania")
async def play(interaction: discord.Interaction, query: str):
    member_channel(interaction)
    kind, value = parse_query(query)
    await interaction.response.defer(thinking=True)
    # Serializacja zachowuje kolejność równoczesnych importów na tym samym serwerze.
    async with bot.locks[interaction.guild_id]:
        member_channel(interaction)
        old = bot.players.get(interaction.guild_id)
        if old and old.voice.is_connected():
            active_player(interaction)
        if kind in ("playlist", "track"):
            tracks, skipped = await bot.spotify.tracks(kind, value)
        else:
            tracks = await bot.resolver.tracks(value, kind)
            skipped = 0
        channel = member_channel(interaction)
        if old and old.voice.is_connected():
            player = active_player(interaction)
        else:
            if old:
                await old.close()
            permissions = channel.permissions_for(interaction.guild.me)
            if not permissions.connect or not permissions.speak:
                raise MusicError("Potrzebuję uprawnień Connect i Speak na Twoim kanale głosowym.")
            try:
                voice = await channel.connect(timeout=30, reconnect=True, self_deaf=True)
            except (discord.DiscordException, TimeoutError):
                raise MusicError("Nie udało się dołączyć do kanału. Sprawdź uprawnienia i połączenie głosowe.") from None
            player = Player(voice, interaction.channel, bot.resolver, bot.ffmpeg)
            bot.players[interaction.guild_id] = player
        player.add(tracks)
        suffix = f" Pominięto niedostępne pozycje: {skipped}." if skipped else ""
        await interaction.followup.send(f"✅ Dodano **{len(tracks)}** utworów w kolejności playlisty.{suffix}")


@bot.tree.command(name="skip", description="Pomiń aktualnie odtwarzany utwór")
@app_commands.guild_only()
async def skip(interaction: discord.Interaction):
    player = active_player(interaction)
    if not player.voice.is_playing() and not player.voice.is_paused():
        raise MusicError("Utwór jest jeszcze wyszukiwany albo kolejka jest pusta. Spróbuj za chwilę lub użyj /stop.")
    player.voice.stop()
    await interaction.response.send_message("⏭️ Pominięto utwór.")


@bot.tree.command(name="pause", description="Wstrzymaj odtwarzanie")
@app_commands.guild_only()
async def pause(interaction: discord.Interaction):
    player = active_player(interaction)
    if not player.voice.is_playing():
        raise MusicError("Żaden utwór nie jest teraz odtwarzany.")
    player.voice.pause()
    await interaction.response.send_message("⏸️ Pauza.")


@bot.tree.command(name="resume", description="Wznów odtwarzanie")
@app_commands.guild_only()
async def resume(interaction: discord.Interaction):
    player = active_player(interaction)
    if not player.voice.is_paused():
        raise MusicError("Odtwarzanie nie jest wstrzymane.")
    player.voice.resume()
    await interaction.response.send_message("▶️ Wznowiono.")


@bot.tree.command(name="stop", description="Wyczyść kolejkę i rozłącz bota")
@app_commands.guild_only()
async def stop(interaction: discord.Interaction):
    active_player(interaction)
    await interaction.response.defer()
    async with bot.locks[interaction.guild_id]:
        player = active_player(interaction)
        await player.close()
        bot.players.pop(interaction.guild_id, None)
    await interaction.followup.send("⏹️ Kolejka usunięta. Rozłączono bota.")


@bot.tree.command(name="queue", description="Pokaż bieżący utwór i kolejne pozycje")
@app_commands.guild_only()
async def queue(interaction: discord.Interaction):
    if not interaction.guild_id:
        raise MusicError("Użyj komendy na serwerze.")
    player = bot.players.get(interaction.guild_id)
    if not player or not player.voice.is_connected():
        await interaction.response.send_message("Kolejka jest pusta.", ephemeral=True)
        return
    # Odczyt snapshotu nie zmienia kolejki; wszystkie operacje biegną na jednej pętli asyncio.
    upcoming = list(player.queue._queue)
    current = player.current.title if player.current else "Oczekiwanie"
    lines = [f"**Teraz:** {discord.utils.escape_markdown(current)[:180]}"]
    lines += [f"{index}. {discord.utils.escape_markdown(track.title)[:90]}" for index, track in enumerate(upcoming[:10], 1)]
    lines.append(f"\nOczekuje: {len(upcoming)} utworów.")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.error
async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)
    if isinstance(original, MusicError):
        message = str(original)
    else:
        log.error("Komenda nie powiodła się: %s", type(original).__name__)
        message = "Nie udało się wykonać komendy. Sprawdź połączenie i konfigurację bota."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        log.warning("Nie udało się dostarczyć odpowiedzi na komendę.")


def main():
    parser = argparse.ArgumentParser(description="BOTspoti — bot muzyczny Discord")
    parser.add_argument("--check", action="store_true", help="Sprawdź lokalną konfigurację bez logowania do Discorda")
    args = parser.parse_args()
    missing = []
    for name in ("DISCORD_TOKEN", "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"):
        present = bool(os.getenv(name, "").strip())
        print(f"{name}: {'ustawione' if present else 'BRAK'}")
        if not present:
            missing.append(name)
    ffmpeg_ok = shutil.which(bot.ffmpeg) is not None
    print(f"FFmpeg: {'OK' if ffmpeg_ok else 'BRAK'}")
    guild = os.getenv("DISCORD_GUILD_ID", "")
    valid_guild = not guild or (guild.isdigit() and int(guild) > 0)
    print(f"DISCORD_GUILD_ID: {'OK (komendy globalne)' if not guild else ('OK' if valid_guild else 'NIEPOPRAWNY')}")
    if not ffmpeg_ok or not valid_guild or (missing and args.check) or "DISCORD_TOKEN" in missing:
        raise SystemExit(1)
    if args.check:
        print("Konfiguracja lokalna poprawna. Ten test nie sprawdza uprawnień API ani połączenia głosowego.")
        return
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        bot.run(os.environ["DISCORD_TOKEN"], log_handler=None)
    except discord.LoginFailure:
        raise SystemExit("Discord odrzucił token bota. Sprawdź DISCORD_TOKEN w .env.") from None


if __name__ == "__main__":
    main()
