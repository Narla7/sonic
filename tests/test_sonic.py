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

    @unittest.skipUnless(sonic.HAVE_PIL, "Pillow required")
    def test_render_fills_panel_half_blocks(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            Image.new("RGB", (100, 100), (200, 100, 50)).save(
                os.path.join(d, "art.jpg"))
            cover = sonic.CoverArt(d, ["art.jpg"])
            cover.set_manual("art.jpg")
            cover.set_track(os.path.join(d, "song.mp3"))
            cols, rows = 30, 12
            grid = cover.render(cols, rows, True, 256)
            self.assertEqual(len(grid), rows)
            for row in grid:
                self.assertEqual(len(row), cols)
                for fg, bg, ch in row:
                    self.assertEqual(ch, "▀")
                    self.assertIsInstance(fg, int)
                    self.assertIsInstance(bg, int)

    @unittest.skipUnless(sonic.HAVE_PIL, "Pillow required")
    def test_render_mono_ascii(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            Image.new("RGB", (50, 50), (255, 255, 255)).save(
                os.path.join(d, "art.png"))
            cover = sonic.CoverArt(d, ["art.png"])
            cover.set_manual("art.png")
            cover.set_track(os.path.join(d, "song.mp3"))
            grid = cover.render(20, 8, False, 0)
            self.assertEqual(len(grid), 8)
            chars = {ch for row in grid for _, _, ch in row}
            self.assertTrue(chars <= set(sonic._ASCII_RAMP))


class TestKitty(unittest.TestCase):
    def test_is_kitty(self):
        self.assertTrue(sonic.is_kitty({"TERM": "xterm-kitty"}))
        self.assertTrue(sonic.is_kitty({"TERM": "x",
                                        "KITTY_WINDOW_ID": "1"}))
        self.assertFalse(sonic.is_kitty({"TERM": "xterm-256color"}))

    def test_transmit_roundtrip(self):
        import base64
        png = b"\x89PNG\r\n" + bytes(9000)
        cmds = sonic.kitty_transmit_cmds(7, png)
        self.assertGreater(len(cmds), 1)
        self.assertTrue(cmds[0].startswith(b"\x1b_Ga=t,i=7,f=100,q=2,m=1;"))
        self.assertTrue(cmds[-1].startswith(b"\x1b_Ga=t,i=7,f=100,q=2,m=0;"))
        payload = b"".join(c.split(b";", 1)[1][:-2] for c in cmds)
        self.assertEqual(payload, base64.b64encode(png))
        for c in cmds:
            self.assertEqual(len(c.split(b";", 1)[1][:-2]), 4096
                             if c is not cmds[-1] else len(payload) % 4096 or 4096)

    def test_place_delete_cup(self):
        self.assertEqual(sonic.kitty_place_cmd(7, 37, 19),
                         b"\x1b_Ga=p,i=7,c=37,r=19,q=2\x1b\\")
        self.assertEqual(sonic.kitty_delete_cmd(7),
                         b"\x1b_Ga=d,d=i,i=7,q=2\x1b\\")
        self.assertEqual(sonic.kitty_cup_cmd(1, 42), b"\x1b[2;43H")

    @unittest.skipUnless(sonic.HAVE_PIL, "Pillow required")
    def test_kitty_png_and_sync(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            Image.new("RGB", (100, 100), (10, 20, 30)).save(
                os.path.join(d, "art.jpg"))
            ui = sonic.UI(FakeStdscr(), [sonic.Track("a.mp3", "A")],
                          d, engine=FakeEngine())
            ui.kitty_art = True  # force: headless TERM may vary
            ui.cover.set_manual("art.jpg")
            ui.cover.set_track(os.path.join(d, "song.mp3"))
            png = ui.cover.kitty_png()
            self.assertTrue(png.startswith(b"\x89PNG"))
            ui._sync_kitty((1, 40, 30, 10))
            self.assertGreaterEqual(len(ui._kitty_pending), 3)
            self.assertEqual(ui._kitty_placed, (1, 1, 40, 30, 10))
            ui._kitty_pending = []
            ui._sync_kitty((1, 40, 30, 10))
            self.assertEqual(ui._kitty_pending, [])  # quiet when unchanged
            ui._sync_kitty((1, 40, 30, 9))
            self.assertEqual(len(ui._kitty_pending), 2)  # re-place only
            ui._kitty_pending = []
            ui._sync_kitty(None)
            self.assertEqual(len(ui._kitty_pending), 1)  # delete on hide
            self.assertIsNone(ui._kitty_placed)


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

    def test_art_always_square(self):
        # Displayed proportions must be square at any window size:
        # width == height-in-rows * cell aspect.
        for h, w in [(24, 80), (24, 120), (40, 120), (50, 200),
                     (14, 76), (14, 200), (30, 90)]:
            layout = sonic.compute_layout(h, w, True)
            self.assertGreater(layout["panel_w"], 0)
            self.assertEqual(layout["art_w"],
                             layout["art_h"] * sonic.CELL_ASPECT)

    def test_art_centered_when_tall(self):
        # Width-capped square on a tall window: centered vertically.
        layout = sonic.compute_layout(50, 90, True)
        avail = 50 - 5
        self.assertEqual(layout["art_y"], 1 + (avail - layout["art_h"]) // 2)
        self.assertGreater(layout["art_y"], 1)

    def test_art_maximal_on_tall_window(self):
        # Tall + wide: art claims everything the list doesn't need.
        layout = sonic.compute_layout(40, 120, True, need_w=45)
        self.assertEqual((layout["art_w"], layout["art_h"]), (70, 35))
        self.assertGreaterEqual(layout["list_w"], 45)

    def test_list_keeps_title_width(self):
        layout = sonic.compute_layout(30, 100, True, need_w=70)
        self.assertGreaterEqual(layout["list_w"], 50)  # need capped at w/2
        self.assertGreater(layout["art_w"], 0)

    def test_huge_need_capped_at_half(self):
        # Absurdly long titles can't kill the art panel.
        layout = sonic.compute_layout(24, 120, True, need_w=500)
        self.assertGreater(layout["panel_w"], 0)
        self.assertGreater(layout["art_w"], 0)
        self.assertEqual(layout["art_w"], layout["art_h"] * sonic.CELL_ASPECT)

    def test_art_shrinks_when_short(self):
        layout = sonic.compute_layout(14, 200, True)
        self.assertLessEqual(layout["art_h"], 14 - 5)
        self.assertEqual(layout["art_w"], layout["art_h"] * sonic.CELL_ASPECT)


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

    def test_resize_key(self):
        import curses
        ui = self._ui()

        class Scr:
            cleared = False

            def clear(self):
                self.cleared = True

        ui.stdscr = Scr()
        self.assertTrue(ui.handle_key(curses.KEY_RESIZE))
        self.assertTrue(ui.stdscr.cleared)

    def test_need_list_w(self):
        ui = sonic.UI(FakeStdscr(),
                      [sonic.Track("a.mp3", "A Very Long Title Here", "B"),
                       sonic.Track("b.mp3", "C")],
                      "/tmp", engine=FakeEngine())
        need = ui._need_list_w()
        self.assertGreaterEqual(need, len("B - A Very Long Title Here"))
        layout = sonic.compute_layout(24, 200, True, need)
        self.assertGreaterEqual(layout["list_w"], need)

    def test_quit(self):
        ui = self._ui()
        self.assertFalse(ui.handle_key(ord("q")))
        self.assertFalse(ui.handle_key(27))


if __name__ == "__main__":
    unittest.main()
