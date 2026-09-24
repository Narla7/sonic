"""Unit tests for sonic's pure helpers and new visualizer/art logic."""

import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sonic


class FakeStdscr:
    def getmaxyx(self):
        return (24, 80)


class FakeEngine:
    state = sonic.Engine.STOPPED
    ended = False
    position = 0.0
    length = 0.0

    def set_volume(self, v):
        pass

    def load(self, p):
        pass

    def pause_toggle(self):
        pass

    def stop(self):
        pass

    def seek(self, d):
        pass

    def poll(self):
        pass

    def quit(self):
        pass


class FakeAnalyzer:
    bars = sonic.BARS_MAX
    levels = [0.0] * sonic.BARS_MAX
    active = False

    def load(self, p):
        pass

    def pause_toggle(self):
        pass

    def stop(self):
        pass

    def seek(self, d):
        pass

    def poll(self):
        pass

    def quit(self):
        pass


class TestHelpers(unittest.TestCase):
    def test_natural_sort(self):
        names = ["10.mp3", "2.mp3", "1.mp3", "20.mp3"]
        names.sort(key=sonic.natural_key)
        self.assertEqual(names, ["1.mp3", "2.mp3", "10.mp3", "20.mp3"])

    def test_format_time(self):
        self.assertEqual(sonic.format_time(0), "0:00")
        self.assertEqual(sonic.format_time(65), "1:05")
        self.assertEqual(sonic.format_time(-3), "0:00")

    def test_progress_bar(self):
        self.assertEqual(sonic.progress_bar(0.0, 4), "----")
        self.assertEqual(sonic.progress_bar(1.0, 4), "####")
        self.assertEqual(sonic.progress_bar(1.5, 4), "####")
        self.assertEqual(sonic.progress_bar(-1.0, 4), "----")

    def test_track_display(self):
        t = sonic.Track(path="x", title="Rain", artist="BoC")
        self.assertEqual(t.display, "BoC - Rain")


class TestFindCover(unittest.TestCase):
    def test_same_stem_wins(self):
        self.assertEqual(
            sonic.find_cover("/x/02 b.mp3", ["02 b.png", "cover.jpg"]),
            "02 b.png")

    def test_cover_names(self):
        self.assertEqual(
            sonic.find_cover("/x/song.mp3", ["folder.jpg"]), "folder.jpg")

    def test_single_fallback(self):
        self.assertEqual(
            sonic.find_cover("/x/song.mp3", ["poster.png"]), "poster.png")

    def test_none(self):
        self.assertIsNone(sonic.find_cover("/x/song.mp3", []))
        self.assertIsNone(sonic.find_cover("/x/song.mp3",
                                           ["cover.txt"]))

    def test_any_image_fallback(self):
        # Any image in the folder counts as album art.
        self.assertEqual(sonic.find_cover("/x/song.mp3",
                                          ["a.png", "b.png", "cover.txt"]),
                         "a.png")


class TestScanArt(unittest.TestCase):
    def test_scan_dir(self):
        with tempfile.TemporaryDirectory() as d:
            for n in ("a.mp3", "cover.JPG", "poster.png", "notes.txt"):
                open(os.path.join(d, n), "w").close()
            os.mkdir(os.path.join(d, "sub"))
            open(os.path.join(d, "sub", "nested.png"), "w").close()
            self.assertEqual(sonic.scan_album_art(d), ["cover.JPG", "poster.png"])


class TestLayout(unittest.TestCase):
    def test_small_no_panel(self):
        layout = sonic.compute_layout(12, 70, True, True)
        self.assertEqual(layout["panel_w"], 0)
        self.assertEqual(layout["list_w"], 69)

    def test_wide_split(self):
        layout = sonic.compute_layout(24, 120, True, True)
        self.assertGreater(layout["panel_w"], 0)
        self.assertGreater(layout["art_h"], 0)
        self.assertGreater(layout["viz_h"], 0)
        self.assertEqual(layout["art_h"] + layout["viz_h"], 24 - 5)

    def test_art_only(self):
        layout = sonic.compute_layout(24, 120, True, False)
        self.assertGreater(layout["art_h"], 0)
        self.assertEqual(layout["viz_h"], 0)


class TestSpectrum(unittest.TestCase):
    def test_sine_peaks_near_freq(self):
        sine = [int(18000 * math.sin(2 * math.pi * 440 * i / 16000))
                for i in range(1024)]
        mags = sonic.spectrum_magnitudes(sine, 16000, 12)
        self.assertGreater(mags[5], mags[0])
        self.assertGreater(mags[5], mags[11])

    def test_goertzel_matches(self):
        sine = [int(1000 * math.sin(2 * math.pi * 1000 * i / 16000))
                for i in range(1024)]
        self.assertGreater(sonic.goertzel(sine, 1000, 16000),
                           sonic.goertzel(sine, 7000, 16000))


class TestUIKeys(unittest.TestCase):
    def _ui(self):
        return sonic.UI(FakeStdscr(), [sonic.Track("a.mp3", "A")],
                        "/tmp", engine=FakeEngine(), analyzer=FakeAnalyzer())

    def test_toggles(self):
        ui = self._ui()
        self.assertTrue(ui.art_on)
        self.assertTrue(ui.viz_on)
        self.assertTrue(ui.handle_key(ord("a")))
        self.assertFalse(ui.art_on)
        self.assertTrue(ui.handle_key(ord("v")))
        self.assertFalse(ui.viz_on)
        self.assertTrue(ui.handle_key(ord("v")))
        self.assertTrue(ui.viz_on)

    def test_quit(self):
        ui = self._ui()
        self.assertFalse(ui.handle_key(ord("q")))
        self.assertFalse(ui.handle_key(27))


if __name__ == "__main__":
    unittest.main()