import shutil
import unittest

from botspoti.player import OpusSource


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg nie jest zainstalowany")
class FFmpegTests(unittest.TestCase):
    def test_real_ffmpeg_produces_opus_frames(self):
        source = OpusSource("sine=frequency=440:duration=0.1", before_options="-f lavfi", options="-vn -loglevel error")
        try:
            packets = []
            while True:
                packet = source.read()
                if not packet:
                    break
                packets.append(packet)
            self.assertGreater(len(packets), 0)
            self.assertEqual(source.frames, len(packets))
            self.assertTrue(source.is_opus())
        finally:
            source.cleanup()
