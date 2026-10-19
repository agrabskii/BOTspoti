from __future__ import annotations

import asyncio
import time

import aiohttp

from .music import MAX_QUEUE, MusicError, Track


class Spotify:
    def __init__(self, session: aiohttp.ClientSession, client_id: str, client_secret: str):
        self.session = session
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = ""
        self._expires = 0.0
        self._lock = asyncio.Lock()

    async def _authorize(self):
        if not self.client_id or not self.client_secret:
            raise MusicError("Obsługa Spotify wymaga SPOTIFY_CLIENT_ID i SPOTIFY_CLIENT_SECRET w pliku .env operatora bota.")
        async with self._lock:
            if self._expires > time.monotonic():
                return
            async with self.session.post(
                "https://accounts.spotify.com/api/token",
                auth=aiohttp.BasicAuth(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
            ) as response:
                if response.status != 200:
                    raise MusicError("Spotify odrzuciło uwierzytelnienie aplikacji. Operator musi sprawdzić dane w .env.")
                data = await response.json()
            self._token = data["access_token"]
            self._expires = time.monotonic() + max(0, data["expires_in"] - 60)

    async def _get(self, path: str, params=None):
        for attempt in range(2):
            await self._authorize()
            async with self.session.get(
                "https://api.spotify.com/v1/" + path,
                headers={"Authorization": "Bearer " + self._token}, params=params,
            ) as response:
                if response.status == 401 and attempt == 0:
                    self._expires = 0
                    continue
                if response.status in (403, 404):
                    raise MusicError("Spotify nie udostępnia tej playlisty/utworu tej aplikacji. Sprawdź publiczną widoczność i dostęp aplikacji do API; sam publiczny link nie gwarantuje uprawnień.")
                if response.status == 429:
                    raise MusicError("Limit zapytań Spotify. Spróbuj później — nic nie dodano.")
                if response.status != 200:
                    raise MusicError("Spotify jest chwilowo niedostępne. Spróbuj ponownie później.")
                return await response.json()
        raise MusicError("Sesja Spotify wygasła. Sprawdź konfigurację aplikacji.")

    async def tracks(self, kind: str, identifier: str) -> tuple[list[Track], int]:
        try:
            if kind == "track":
                raw = [await self._get("tracks/" + identifier)]
            else:
                raw = []
                offset = 0
                while True:
                    # Pobieramy wszystkie strony aktualnego endpointu playlist items.
                    page = await self._get(f"playlists/{identifier}/items", {"limit": 50, "offset": offset})
                    items = page.get("items", [])
                    raw.extend(item.get("track") or item.get("item") for item in items if item)
                    if len(raw) > MAX_QUEUE:
                        raise MusicError(f"Playlista przekracza limit {MAX_QUEUE} pozycji; nic nie dodano.")
                    if not page.get("next"):
                        break
                    if not items:
                        raise MusicError("Spotify zwróciło niekompletną playlistę; nic nie dodano.")
                    offset += len(items)
        except (aiohttp.ClientError, TimeoutError):
            raise MusicError("Brak połączenia ze Spotify. Sprawdź sieć i spróbuj ponownie.") from None
        tracks = []
        skipped = 0
        for item in raw:
            if not item or item.get("type") != "track" or item.get("is_local") or item.get("is_playable") is False:
                skipped += 1
                continue
            artists = ", ".join(a["name"] for a in item.get("artists", []))
            title = item.get("name")
            if not title or not artists:
                skipped += 1
                continue
            label = f"{artists} — {title}"
            tracks.append(Track(label, f"ytsearch1:{artists} {title} audio", (item.get("duration_ms") or 0) / 1000 or None, True))
        if not tracks:
            raise MusicError("Brak dostępnych utworów. Playlista może być pusta, prywatna lub niedostępna przez API.")
        return tracks, skipped
