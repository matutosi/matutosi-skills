#!/usr/bin/env python3
"""video-highlight のスクリプトの自己テスト.

    python tests/test_video_highlight.py

区間の組み立て・無音の検出・切り口の寄せ方は numpy だけで試す．
ffmpeg があれば，色と音で作った 10 秒の動画で analyze → render を通しで試す
(書き起こしは飛ばす．faster-whisper は要らない)．
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "scripts", "video_highlight.py")
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import video_highlight as vh  # noqa: E402

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


class SnapTest(unittest.TestCase):
    SIL = [[2.0, 3.0], [6.0, 6.5]]

    def test_start_inside_silence_moves_to_its_end(self):
        self.assertAlmostEqual(vh.snap(2.5, self.SIL, True), 2.75)

    def test_end_inside_silence_moves_to_its_start(self):
        self.assertAlmostEqual(vh.snap(2.5, self.SIL, False), 2.25)

    def test_end_never_moves_back_over_speech(self):
        # silence 2.0-3.0 lies before t = 3.4: the end must not jump back into it
        self.assertGreaterEqual(vh.snap(3.4, self.SIL, False), 3.4)

    def test_start_never_moves_forward_over_speech(self):
        # silence 6.0-6.5 starts after t = 5.6: the start must not jump into it
        self.assertLessEqual(vh.snap(5.6, self.SIL, True), 5.6)

    def test_no_silence_nearby_pads(self):
        self.assertAlmostEqual(vh.snap(10.0, self.SIL, True), 10.0 - vh.PAD)
        self.assertAlmostEqual(vh.snap(10.0, self.SIL, False), 10.0 + vh.PAD)


class ResolveTest(unittest.TestCase):
    SEGS = {1: {"start": 0.0, "end": 4.0}, 2: {"start": 4.0, "end": 8.0},
            3: {"start": 8.0, "end": 12.0}, 4: {"start": 20.0, "end": 25.0}}

    def test_adjacent_ids_are_joined_and_sorted(self):
        spans = vh.resolve({"keep": [4, 2, 1]}, self.SEGS, 30.0, [])
        self.assertEqual(len(spans), 2)
        self.assertLess(spans[0][0], spans[1][0])
        self.assertAlmostEqual(spans[0][1], 8.0 + vh.PAD)

    def test_partial_and_explicit_times(self):
        spans = vh.resolve({"keep": [{"id": 3, "start": 10.0}, {"start": 26.0, "end": 27.0}]},
                           self.SEGS, 30.0, [])
        self.assertAlmostEqual(spans[0][0], 10.0 - vh.PAD)
        self.assertAlmostEqual(spans[1][1], 27.0 + vh.PAD)

    def test_clamped_to_duration(self):
        spans = vh.resolve({"keep": [4]}, self.SEGS, 25.0, [])
        self.assertLessEqual(spans[0][1], 25.0)


class SegmentTest(unittest.TestCase):
    def test_gaps_split_at_cuts_and_max_length(self):
        speech = [{"start": 0.0, "end": 5.0, "text": "a"}]
        level = np.full(int(40 / vh.FRAME), -20.0)
        segs = vh.build_segments(40.0, speech, [15.0], level)
        self.assertEqual(segs[0]["kind"], "speech")
        gaps = [s for s in segs if s["kind"] == "gap"]
        self.assertTrue(all(s["dur"] <= vh.MAX_SEG + 1e-6 for s in gaps))
        self.assertIn(15.0, [s["start"] for s in gaps])
        self.assertAlmostEqual(sum(s["dur"] for s in segs), 40.0, places=1)
        self.assertEqual([s["id"] for s in segs], list(range(1, len(segs) + 1)))

    def test_silences_found_in_tone_with_gaps(self):
        t = np.arange(int(vh.SR * 6)) / vh.SR
        audio = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        audio[int(vh.SR * 2):int(vh.SR * 3)] = 0.0
        level = vh.loudness(audio, 6.0)
        sil = vh.silences(audio, level)
        self.assertEqual(len(sil), 1)
        self.assertAlmostEqual(sil[0][0], 2.0, delta=0.5)
        self.assertAlmostEqual(sil[0][1], 3.0, delta=0.5)


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg が無い")
class EndToEndTest(unittest.TestCase):
    """red 5 s then blue 5 s; a tone that is silent for 1 s out of every 4 s."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="vh_test_")
        cls.video = os.path.join(cls.tmp, "sample.mp4")
        r = subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=160x120:r=25:d=5",
            "-f", "lavfi", "-i", "color=c=blue:s=160x120:r=25:d=5",
            "-f", "lavfi", "-i", "aevalsrc='if(lt(mod(t,4),3),0.4*sin(2*PI*440*t),0)':s=44100:d=10",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", cls.video], capture_output=True, text=True)
        if r.returncode != 0:
            raise unittest.SkipTest("サンプル動画を作れない: " + r.stderr[-200:])
        cls.out = os.path.join(cls.tmp, "work")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_script(self, *args):
        r = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout

    def test_analyze_then_render(self):
        self.run_script("analyze", self.video, "--out", self.out, "--no-transcribe")
        data = json.load(open(os.path.join(self.out, "segments.json"), encoding="utf-8"))
        self.assertAlmostEqual(data["info"]["duration"], 10.0, delta=0.2)
        self.assertTrue(any(abs(c - 5.0) < 0.2 for c in data["scene_cuts"]))
        self.assertGreaterEqual(len(data["silences"]), 2)
        self.assertTrue(os.path.exists(os.path.join(self.out, "summary.md")))
        self.assertTrue(data["sheets"])

        with open(os.path.join(self.out, "selection.json"), "w", encoding="utf-8") as f:
            # silences are 3-4 s and 7-8 s; cuts snap 0.25 s into them:
            # 0-3 -> 0-3.25 and 8-10 -> 7.75-10, 5.5 s in all
            json.dump({"target": 5.5, "keep": [{"start": 0.0, "end": 3.0},
                                               {"start": 8.0, "end": 10.0}]}, f)
        log = self.run_script("render", "--out", self.out, "--name", "short.mp4")
        self.assertIn("2 pieces", log)
        got = vh.probe(__import__("pathlib").Path(self.out, "short.mp4"))
        self.assertAlmostEqual(got["duration"], 5.5, delta=0.4)
        self.assertTrue(got["has_audio"] and got["has_video"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
