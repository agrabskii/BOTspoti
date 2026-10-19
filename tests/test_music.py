import unittest
from unittest.mock import AsyncMock

from botspoti.music import AudioResolver, MAX_QUEUE, MusicError, Track, parse_query


ID = "1234567890abcdefghijkl"


class QueryTests(unittest.TestCase):
    def test_spotify_link_with_tracking_and_locale(self):
        self.assertEqual(parse_query(f"https://open.spotify.com/intl-pl/playlist/{ID}?si=abc"), ("playlist", ID))

    def test_spotify_track_uri(self):
        self.assertEqual(parse_query("spotify:track:" + ID), ("track", ID))

    def test_search(self):
        self.assertEqual(parse_query("Daft Punk Get Lucky"), ("search", "Daft Punk Get Lucky"))

    def test_reject_untrusted_links(self):
        for link in ("http://youtube.com/watch?v=a", "https://127.0.0.1/secret", "file:///etc/passwd", "https://youtube.com.evil.example", "https://x:secret@youtube.com/", "https://youtube.com:bad/", "", "https://open.spotify.com/album/" + ID):
            with self.subTest(link=link), self.assertRaises(MusicError):
                parse_query(link)


class AudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_youtube_playlist_order(self):
        resolver = AudioResolver()
        resolver._extract = AsyncMock(return_value={"_type": "playlist", "entries": [
            {"id": "aaaaaaaaaaa", "title": "First"}, None,
            {"id": "bbbbbbbbbbb", "title": "Second"},
        ]})
        tracks = await resolver.tracks("https://youtube.com/playlist?list=example", "youtube")
        self.assertEqual([t.title for t in tracks], ["First", "Second"])
        self.assertEqual(tracks[0].query, "https://www.youtube.com/watch?v=aaaaaaaaaaa")

    async def test_over_limit_not_silently_truncated(self):
        resolver = AudioResolver()
        resolver._extract = AsyncMock(return_value={"_type": "playlist", "entries": [{"id": "aaaaaaaaaaa", "title": "Song"}] * (MAX_QUEUE + 1)})
        with self.assertRaises(MusicError):
            await resolver.tracks("url", "youtube")

    async def test_resolve_fresh_audio_url(self):
        resolver = AudioResolver()
        resolver._extract = AsyncMock(return_value={"entries": [{"url": "https://audio.googlevideo.com/example", "duration": 180}]})
        track = Track("Title", "ytsearch1:title", 180, True)
        self.assertEqual(await resolver.stream(track), "https://audio.googlevideo.com/example")

    async def test_skip_wrong_duration_and_untrusted_stream(self):
        resolver = AudioResolver()
        for data in ({"url": "https://audio.googlevideo.com/example", "duration": 500}, {"url": "http://127.0.0.1/private", "duration": 180}):
            resolver._extract = AsyncMock(return_value=data)
            with self.assertRaises(MusicError):
                await resolver.stream(Track("Title", "query", 180, True))
