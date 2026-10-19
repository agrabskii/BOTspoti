from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import yt_dlp

MAX_QUEUE = 500
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "music.youtube.com", "youtu.be"}


class MusicError(Exception):
    """Komunikat przeznaczony dla użytkownika, bez danych uwierzytelniających."""


@dataclass(frozen=True)
class Track:
    title: str
    query: str
    duration: float | None = None
    spotify: bool = False


def parse_query(value: str) -> tuple[str, str]:
    value = value.strip().strip("<>")
    if not value or len(value) > 2000:
        raise MusicError("Podaj link albo nazwę utworu (maksymalnie 2000 znaków).")
    if value.startswith("spotify:"):
        match = re.fullmatch(r"spotify:(playlist|track):([A-Za-z0-9]{22})", value)
        if not match:
            raise MusicError("Obsługuję linki Spotify do utworów i publicznych playlist.")
        return match.group(1), match.group(2)
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or value.startswith("www."):
        try:
            port = parsed.port
        except ValueError:
            raise MusicError("Nieprawidłowy adres linku.") from None
        if parsed.scheme != "https" or parsed.username or parsed.password or port:
            raise MusicError("Wklej pełny link HTTPS ze Spotify lub YouTube.")
        if parsed.hostname == "open.spotify.com":
            match = re.fullmatch(r"/(?:intl-[a-z]+/)?(playlist|track)/([A-Za-z0-9]{22})/?", parsed.path)
            if match:
                return match.group(1), match.group(2)
            raise MusicError("Obsługuję utwory i publiczne playlisty Spotify, bez albumów i podcastów.")
        if parsed.hostname in YOUTUBE_HOSTS:
            return "youtube", value
        raise MusicError("Obsługuję pełne linki open.spotify.com oraz YouTube; skrócone linki Spotify rozwiń w przeglądarce.")
    return "search", value


class QuietLogger:
    # Nie zapisujemy adresów strumieni i parametrów sesji do logów.
    def debug(self, message):
        pass

    warning = debug
    error = debug


class AudioResolver:
    def __init__(self):
        self._slots = asyncio.Semaphore(2)

    async def _extract(self, query: str, *, flat: bool = False):
        def run():
            options = {
                "format": "bestaudio/best", "quiet": True,
                "logger": QuietLogger(), "noplaylist": not flat,
                "extract_flat": "in_playlist" if flat else False,
                "playlistend": MAX_QUEUE + 1, "socket_timeout": 15,
                "retries": 1, "cachedir": False,
                "js_runtimes": {"node": {}},
            }
            with yt_dlp.YoutubeDL(options) as extractor:
                return extractor.extract_info(query, download=False)
        async with self._slots:
            try:
                return await asyncio.to_thread(run)
            except Exception:
                raise MusicError("Źródło audio jest niedostępne. Sprawdź link; serwis może blokować dostęp bota.") from None

    async def tracks(self, query: str, kind: str) -> list[Track]:
        if kind == "search":
            return [Track(query, "ytsearch1:" + query)]
        data = await self._extract(query, flat=True)
        if not data:
            raise MusicError("Nie znaleziono nagrania.")
        entries = data.get("entries") if data.get("_type") == "playlist" else [data]
        result = []
        for entry in entries or []:
            if not entry or not entry.get("id"):
                continue
            video_id = entry["id"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
                continue
            result.append(Track(entry.get("title") or "Utwór", "https://www.youtube.com/watch?v=" + video_id, entry.get("duration")))
        if len(result) > MAX_QUEUE:
            raise MusicError(f"Playlista jest zbyt duża. Limit wynosi {MAX_QUEUE} utworów; nic nie dodano.")
        if not result:
            raise MusicError("Playlista nie zawiera dostępnych nagrań.")
        return result

    async def stream(self, track: Track) -> str:
        data = await self._extract(track.query)
        if data and data.get("entries") is not None:
            data = next((item for item in data["entries"] if item), None)
        if not data or not data.get("url") or data.get("is_live"):
            raise MusicError("Nie znaleziono dostępnego nagrania audio.")
        duration = data.get("duration")
        if track.spotify and track.duration and duration:
            if abs(duration - track.duration) > max(30, track.duration * 0.2):
                raise MusicError("Znalezione nagranie ma inną długość — pomijam niepewne dopasowanie.")
        parsed = urlparse(data["url"])
        if parsed.scheme != "https" or not (parsed.hostname or "").endswith(".googlevideo.com"):
            raise MusicError("Źródło zwróciło nieobsługiwany adres strumienia.")
        return data["url"]
