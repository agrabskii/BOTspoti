import unittest
from unittest.mock import AsyncMock, MagicMock

from botspoti.music import MusicError
from botspoti.spotify import Spotify


def track(name, **overrides):
    return {"type": "track", "name": name, "artists": [{"name": "Artist"}], "duration_ms": 180000, **overrides}


class SpotifyTests(unittest.IsolatedAsyncioTestCase):
    async def test_paginate_and_filter_without_changing_order(self):
        spotify = Spotify(None, "", "")
        spotify._get = AsyncMock(side_effect=[
            {"items": [{"track": track("One")}, {"track": None}], "next": "more"},
            {"items": [{"item": track("Two")}, {"track": track("Local", is_local=True)}, {"track": {"type": "episode"}}], "next": None},
        ])
        tracks, skipped = await spotify.tracks("playlist", "id")
        self.assertEqual([t.title for t in tracks], ["Artist — One", "Artist — Two"])
        self.assertEqual(skipped, 3)
        self.assertEqual(spotify._get.call_args_list[1].args, ("playlists/id/items", {"limit": 50, "offset": 2}))
        self.assertEqual(tracks[0].duration, 180)
        self.assertTrue(tracks[0].spotify)

    async def test_oversized_playlist_fails_atomically(self):
        spotify = Spotify(None, "", "")
        spotify._get = AsyncMock(return_value={"items": [{"track": track("Song")}] * 501, "next": None})
        with self.assertRaises(MusicError):
            await spotify.tracks("playlist", "id")

    async def test_empty_or_inaccessible_items(self):
        spotify = Spotify(None, "", "")
        spotify._get = AsyncMock(return_value={"items": [], "next": None})
        with self.assertRaises(MusicError):
            await spotify.tracks("playlist", "id")

    async def test_missing_credentials_does_not_call_network(self):
        session = MagicMock()
        spotify = Spotify(session, "", "")
        with self.assertRaises(MusicError):
            await spotify.tracks("playlist", "id")
        session.post.assert_not_called()

    async def test_api_denials_are_not_misreported_as_success(self):
        for status in (403, 404, 429, 500):
            with self.subTest(status=status):
                response = MagicMock(status=status)
                context = MagicMock()
                context.__aenter__ = AsyncMock(return_value=response)
                context.__aexit__ = AsyncMock(return_value=False)
                session = MagicMock()
                session.get.return_value = context
                spotify = Spotify(session, "id", "secret")
                spotify._authorize = AsyncMock()
                with self.assertRaises(MusicError):
                    await spotify.tracks("playlist", "id")
