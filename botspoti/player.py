from __future__ import annotations

import asyncio
import logging

import discord

from .music import MAX_QUEUE, AudioResolver, MusicError, Track

log = logging.getLogger(__name__)


class OpusSource(discord.FFmpegOpusAudio):
    """Wykrywamy również FFmpeg kończący pracę bez wygenerowania audio."""

    def __init__(self, *args, **kwargs):
        self.frames = 0
        super().__init__(*args, **kwargs)

    def read(self):
        frame = super().read()
        if frame:
            self.frames += 1
        return frame

    def cleanup(self):
        # discord.py kończy proces, ale nie zamyka wszystkich uchwytów jego potoków.
        process = getattr(self, "_process", None)
        pipes = [getattr(process, name, None) for name in ("stdout", "stdin", "stderr")]
        try:
            super().cleanup()
        finally:
            for pipe in pipes:
                if pipe is not None:
                    pipe.close()


class Player:
    def __init__(self, voice, channel, resolver: AudioResolver, ffmpeg: str):
        self.voice = voice
        self.channel = channel
        self.resolver = resolver
        self.ffmpeg = ffmpeg
        self.queue: asyncio.Queue[Track] = asyncio.Queue(MAX_QUEUE)
        self.current: Track | None = None
        self.task: asyncio.Task | None = None

    def add(self, tracks: list[Track]):
        if self.queue.qsize() + len(tracks) > MAX_QUEUE:
            raise MusicError(f"W kolejce może być maksymalnie {MAX_QUEUE} oczekujących utworów. Nic nie dodano.")
        for track in tracks:
            self.queue.put_nowait(track)
        if not self.task or self.task.done():
            self.task = asyncio.create_task(self.run())

    async def notify(self, message: str):
        try:
            await self.channel.send(message, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    async def run(self):
        try:
            while self.voice.is_connected():
                self.current = None
                # Rozłączamy pustą kolejkę po 3 minutach.
                try:
                    track = await asyncio.wait_for(self.queue.get(), timeout=180)
                except TimeoutError:
                    await self.voice.disconnect()
                    return
                self.current = track
                try:
                    url = await self.resolver.stream(track)
                    if not self.voice.is_connected():
                        return
                    source = OpusSource(
                        url, executable=self.ffmpeg,
                        before_options="-nostdin -protocol_whitelist https,tls,tcp,crypto -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -rw_timeout 15000000",
                        options="-vn -loglevel quiet",
                    )
                    finished = asyncio.Event()
                    loop = asyncio.get_running_loop()
                    errors = []

                    def after(error):
                        if error:
                            errors.append(error)
                        loop.call_soon_threadsafe(finished.set)

                    try:
                        self.voice.play(source, after=after)
                    except Exception:
                        source.cleanup()
                        raise
                    await self.notify("▶️ " + discord.utils.escape_markdown(track.title)[:300])
                    await finished.wait()
                    if errors or not source.frames:
                        await self.notify("⚠️ Błąd przesyłania audio. Przechodzę do następnego utworu.")
                except MusicError as error:
                    await self.notify(f"⏭️ Pomijam **{discord.utils.escape_markdown(track.title)[:180]}**: {error}")
                except (discord.DiscordException, OSError):
                    await self.notify("⚠️ Nie udało się uruchomić audio. Sprawdź FFmpeg i połączenie głosowe.")
                except Exception as error:
                    log.error("Błąd odtwarzania: %s", type(error).__name__)
                    await self.notify("⚠️ Błąd odtwarzania. Przechodzę do następnego utworu.")
                finally:
                    self.queue.task_done()
        finally:
            self.current = None

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.voice.stop()
        if self.voice.is_connected():
            await self.voice.disconnect()
