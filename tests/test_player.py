import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from botspoti.music import MAX_QUEUE, MusicError, Track
from botspoti.player import Player


class PlayerTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_skips_to_next_and_stop_disconnects(self):
        voice = MagicMock()
        voice.is_connected.return_value = True
        voice.disconnect = AsyncMock()
        resolver = MagicMock()
        resolver.stream = AsyncMock(side_effect=[MusicError("Unavailable"), "https://audio.googlevideo.com/test"])
        channel = MagicMock()
        channel.send = AsyncMock()
        played = asyncio.Event()

        def play(source, after):
            played.set()
            after(None)

        voice.play.side_effect = play
        player = Player(voice, channel, resolver, "ffmpeg")
        with patch("botspoti.player.OpusSource"):
            player.add([Track("Missing", "first"), Track("Available", "second")])
            await asyncio.wait_for(played.wait(), timeout=2)
            await asyncio.wait_for(player.queue.join(), timeout=2)
            await player.close()
        self.assertEqual(resolver.stream.await_count, 2)
        voice.play.assert_called_once()
        voice.disconnect.assert_awaited_once()
        self.assertIsNone(player.current)
        self.assertTrue(any("Pomijam" in call.args[0] for call in channel.send.call_args_list))

    async def test_queue_capacity_is_atomic(self):
        player = Player(MagicMock(), MagicMock(), MagicMock(), "ffmpeg")
        # Bez uruchamiania odtwarzacza napełniamy kolejkę do limitu.
        for _ in range(MAX_QUEUE - 1):
            player.queue.put_nowait(Track("Existing", "query"))
        with self.assertRaises(MusicError):
            player.add([Track("One", "1"), Track("Two", "2")])
        self.assertEqual(player.queue.qsize(), MAX_QUEUE - 1)

    async def test_stopping_during_resolution_does_not_start_audio(self):
        voice = MagicMock()
        voice.is_connected.return_value = True
        voice.disconnect = AsyncMock()
        resolving = asyncio.Event()

        async def resolve(track):
            resolving.set()
            await asyncio.Event().wait()

        resolver = MagicMock()
        resolver.stream = resolve
        player = Player(voice, MagicMock(), resolver, "ffmpeg")
        player.add([Track("Song", "query")])
        await asyncio.wait_for(resolving.wait(), 2)
        await player.close()
        voice.play.assert_not_called()
        voice.disconnect.assert_awaited_once()
