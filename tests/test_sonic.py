"""Unit tests for sonic's pure helpers and album-art logic."""

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


class TestArtChoices(unittest.TestCase):
    def test_folder_only(self):
        self.assertEqual(
            sonic.build_art_choices(["b.png", "a.jpg"], False),
            ["a.jpg", "b.png"])

    def test_embedded_appended(self):
        self.assertEqual(
            sonic.build_art_choices(["b.png"], True),
            ["b.png", sonic.EMBEDDED_CHOICE])

    def test_non_images_filtered(self):
        self.assertEqual(sonic.build_art_choices(["x.txt"], False), [])
        self.assertEqual(sonic.build_art_choices(["x.txt"], True),
                         [sonic.EMBEDDED_CHOICE])

    def test_labels(self):
        self.assertEqual(sonic.choice_label(sonic.EMBEDDED_CHOICE),
                         "Embedded cover (from MP3 tags)")
        self.assertEqual(sonic.choice_label("cover.jpg"), "cover.jpg")


class TestCoverArt(unittest.TestCase):
    def test_manual_file_selection(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.jpg"), "w").close()
            open(os.path.join(d, "b.jpg"), "w").close()
            cover = sonic.CoverArt(d, ["a.jpg", "b.jpg"])
            self.assertIsNone(cover.manual)
            cover.set_manual("b.jpg")
            cover.set_track(os.path.join(d, "song.mp3"))
            self.assertEqual(cover.path, os.path.join(d, "b.jpg"))

    def test_manual_cleared_on_missing(self):
        with tempfile.TemporaryDirectory() as d:
            cover = sonic.CoverArt(d, ["a.jpg"])
            cover.set_manual("a.jpg")
            cover.refresh_images([])
            self.assertIsNone(cover.manual)


class TestLayout(unittest.TestCase):
    def test_small_no_panel(self):
        layout = sonic.compute_layout(12, 70, True)
        self.assertEqual(layout["panel_w"], 0)
        self.assertEqual(layout["list_w"], 69)

    def test_wide_split(self):
        layout = sonic.compute_layout(24, 120, True)
        self.assertGreater(layout["panel_w"], 0)
        self.assertGreater(layout["art_h"], 0)

    def test_art_off(self):
        layout = sonic.compute_layout(24, 120, False)
        self.assertEqual(layout["panel_w"], 0)
        self.assertEqual(layout["art_h"], 0)


class TestUIKeys(unittest.TestCase):
    def _ui(self):
        return sonic.UI(FakeStdscr(), [sonic.Track("a.mp3", "A")],
                        "/tmp", engine=FakeEngine())

    def test_art_defaults_off(self):
        ui = self._ui()
        self.assertFalse(ui.art_on)

    def test_no_viz_key(self):
        ui = self._ui()
        # 'v' is unmapped now; state unchanged, loop continues.
        self.assertTrue(ui.handle_key(ord("v")))
        self.assertFalse(ui.art_on)

    def test_quit(self):
        ui = self._ui()
        self.assertFalse(ui.handle_key(ord("q")))
        self.assertFalse(ui.handle_key(27))


if __name__ == "__main__":
    unittest.main()
