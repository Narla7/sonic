#!/usr/bin/env python3
"""sonic - a minimal CLI mp3 player for the current directory.

Usage:
    cd ~/Music && sonic

Requires: mpg123 on PATH. Optional: tinytag (for ID3 title/artist display).
"""

import argparse
import curses
import io
import os
import random
import re
import select
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

VERSION = "0.2.0"

SEEK_STEP = 5          # seconds per left/right press
VOLUME_STEP = 5        # percent per +/- press
POLL_INTERVAL = 0.05   # UI tick, seconds

# Album art
IMAGE_EXTS = (".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp", ".gif",
              ".tif", ".tiff", ".avif")
COVER_NAMES = ("cover", "folder", "album", "front", "artwork", "poster",
               "thumb", "thumbnail")

try:
    from tinytag import TinyTag

    HAVE_TINYTAG = True
except ImportError:  # degrade gracefully to filenames
    HAVE_TINYTAG = False

try:
    from PIL import Image as _PILImage
    from PIL import ImageOps as _PILImageOps

    HAVE_PIL = True
except ImportError:  # album art degrades to a placeholder
    _PILImage = None
    _PILImageOps = None
    HAVE_PIL = False


# --------------------------------------------------------------------------
# Tracks
# --------------------------------------------------------------------------

@dataclass
class Track:
    path: str
    title: str
    artist: str = ""
    duration: float = 0.0  # seconds, 0.0 = unknown

    @property
    def display(self) -> str:
        if self.artist:
            return f"{self.artist} - {self.title}"
        return self.title


def natural_key(s: str):
    """Sort key so '2.mp3' comes before '10.mp3'."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def scan_tracks(directory: str) -> list:
    """Return all .mp3 files directly inside directory, naturally sorted."""
    names = [
        n for n in os.listdir(directory)
        if n.lower().endswith(".mp3")
        and os.path.isfile(os.path.join(directory, n))
    ]
    names.sort(key=natural_key)
    tracks = []
    for name in names:
        path = os.path.join(directory, name)
        title = os.path.splitext(name)[0]
        artist = ""
        duration = 0.0
        if HAVE_TINYTAG:
            try:
                tag = TinyTag.get(path)
                if tag.title:
                    title = tag.title
                if tag.artist:
                    artist = tag.artist
                if tag.duration:
                    duration = float(tag.duration)
            except Exception:
                pass  # unreadable tag: stick with the filename
        tracks.append(Track(path=path, title=title, artist=artist,
                            duration=duration))
    return tracks


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def progress_bar(frac: float, width: int) -> str:
    frac = min(1.0, max(0.0, frac))
    filled = int(round(frac * width))
    return "#" * filled + "-" * (width - filled)


# --------------------------------------------------------------------------
# Album art (folder-based + embedded)
# --------------------------------------------------------------------------

EMBEDDED_CHOICE = "__embedded__"

def scan_album_art(directory: str) -> list:
    """Image files directly inside `directory`, ignoring subfolders."""
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    return sorted(
        n for n in names
        if os.path.splitext(n)[1].lower() in IMAGE_EXTS
        and os.path.isfile(os.path.join(directory, n))
    )


def find_cover(track_path: str, image_names: list) -> str | None:
    """Pick the best cover image name for a track from folder images.

    Precedence: same base name -> cover/folder/album/front (exact, then
    prefix/substring, e.g. "Cover Art.jpg", "albumart.png", "front-cover.jpg")
    -> first image in the folder (any image counts as album art).
    """
    if not image_names:
        return None
    images = sorted(
        n for n in image_names
        if os.path.splitext(n)[1].lower() in IMAGE_EXTS
    )
    if not images:
        return None
    stem = os.path.splitext(os.path.basename(track_path))[0].lower()
    for name in images:
        if os.path.splitext(name)[0].lower() == stem:
            return name
    # Exact cover-name match ("cover.jpg", "Folder.PNG", ...).
    for cover in COVER_NAMES:
        for name in images:
            if os.path.splitext(name)[0].lower() == cover:
                return name
    # Affixed cover names ("cover-art.jpg", "albumart.png", "my folder (1).jpg").
    for cover in COVER_NAMES:
        for name in images:
            img_stem = os.path.splitext(name)[0].lower()
            if cover in img_stem:
                return name
    # Any image in the folder counts as album art: deterministic fallback.
    return images[0]


def get_embedded_image(track_path: str) -> bytes | None:
    """Return embedded cover bytes for a track, or None.

    Uses tinytag (`images.any.data`, with a `get_image()` fallback).
    One file read per call; callers should only invoke it on demand
    (track change / picker open), never per UI tick.
    """
    if not HAVE_TINYTAG:
        return None
    try:
        tag = TinyTag.get(track_path, image=True)
    except Exception:
        return None
    try:
        images = getattr(tag, "images", None)
        if images is not None:
            for attr in ("any", "front_cover", "back_cover", "other", "media"):
                try:
                    img = getattr(images, attr, None)
                except Exception:
                    continue
                if img is None:
                    continue
                if isinstance(img, bytes) and img:
                    return img
                data = getattr(img, "data", None)
                if isinstance(data, bytes) and data:
                    return data
                if isinstance(img, (list, tuple)):
                    for item in img:
                        if isinstance(item, bytes) and item:
                            return item
                        d = getattr(item, "data", None)
                        if isinstance(d, bytes) and d:
                            return d
        get_image = getattr(tag, "get_image", None)
        if callable(get_image):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                try:
                    data = get_image()
                except Exception:
                    data = None
            if isinstance(data, bytes) and data:
                return data
    except Exception:
        return None
    return None


def build_art_choices(image_names: list, has_embedded: bool) -> list:
    """Selectable album-art entries: sorted folder images + embedded opt-in."""
    choices = sorted(
        n for n in (image_names or [])
        if os.path.splitext(n)[1].lower() in IMAGE_EXTS
    )
    if has_embedded:
        choices.append(EMBEDDED_CHOICE)
    return choices


def choice_label(choice: str) -> str:
    if choice == EMBEDDED_CHOICE:
        return "Embedded cover (from MP3 tags)"
    return choice


_ASCII_RAMP = " .:-=+*#%@"
_BASE16_RGB = {
    0: (0, 0, 0), 1: (128, 0, 0), 2: (0, 128, 0), 3: (128, 128, 0),
    4: (0, 0, 128), 5: (128, 0, 128), 6: (0, 128, 128), 7: (192, 192, 192),
    8: (128, 128, 128), 9: (255, 0, 0), 10: (0, 255, 0), 11: (255, 255, 0),
    12: (0, 0, 255), 13: (255, 0, 255), 14: (0, 255, 255), 15: (255, 255, 255),
}


def terminal_palette(ncolors: int) -> list:
    """(color_index, rgb) palettes usable with curses `init_pair`."""
    if ncolors >= 256:
        vals = (0, 95, 135, 175, 215, 255)
        return [(16 + 36 * r + 6 * g + b, (vals[r], vals[g], vals[b]))
                for r in range(6) for g in range(6) for b in range(6)]
    return [(i, _BASE16_RGB[i]) for i in range(16)]


class CoverArt:
    """Renders the user-selected cover (folder image or embedded bytes).

    Nothing is auto-selected: `manual` is only set via the art picker
    (key `a`). Per-track `set_track` then resolves that choice --
    a filename stays constant, `EMBEDDED_CHOICE` reloads each track's tags.
    """

    def __init__(self, directory: str, image_names: list):
        self.directory = directory
        self.image_names = list(image_names)
        self.manual: str | None = None
        self.path: str | None = None
        self._embedded: bytes | None = None
        self._cache: dict = {}
        self.available = bool(HAVE_PIL)

    def set_manual(self, choice: str | None) -> None:
        self.manual = choice
        self.path = None
        self._embedded = None
        self._cache.clear()

    def refresh_images(self, image_names: list) -> None:
        self.image_names = list(image_names)
        if self.manual not in (None, EMBEDDED_CHOICE) and self.manual not in self.image_names:
            self.set_manual(None)

    def set_track(self, track_path: str) -> None:
        if self.manual == EMBEDDED_CHOICE:
            data = get_embedded_image(track_path)
            if data != self._embedded:
                self._cache.clear()
            self._embedded = data
            self.path = None
            return
        if self.manual:
            path = os.path.join(self.directory, self.manual)
            if path != self.path:
                self._cache.clear()
            self.path = path if os.path.isfile(path) else None
            self._embedded = None
            return
        # No manual choice: fall back to the auto best-guess so art still
        # works if a caller never opened the picker.
        name = find_cover(track_path, self.image_names)
        path = os.path.join(self.directory, name) if name else None
        if path != self.path:
            self._cache.clear()
        self.path = path
        self._embedded = None

    def render(self, cols: int, rows: int, use_color: bool, ncolors: int):
        """Return rows of (color_index|None, char) cells, or None if no art."""
        if not self.available:
            return None
        if self.path is None and self._embedded is None:
            return None
        key = (cols, rows, use_color, ncolors)
        if key not in self._cache:
            self._cache[key] = self._render(cols, rows, use_color, ncolors)
        return self._cache[key]

    def _nearest(self, rgb: tuple, palette: list) -> int:
        best, best_d = palette[0][0], 1 << 30
        for idx, prgb in palette:
            d = ((rgb[0] - prgb[0]) ** 2 + (rgb[1] - prgb[1]) ** 2
                 + (rgb[2] - prgb[2]) ** 2)
            if d < best_d:
                best, best_d = idx, d
        return best

    def _render(self, cols: int, rows: int, use_color: bool, ncolors: int) -> list | None:
        palette = terminal_palette(ncolors)
        try:
            if self._embedded is not None:
                img = _PILImage.open(io.BytesIO(self._embedded))
            else:
                img = _PILImage.open(self.path)
            img = _PILImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((max(1, cols), max(1, rows)), _PILImage.Resampling.LANCZOS)
        except Exception:
            return None
        w, h = img.size
        px = img.load()
        offx, offy = (cols - w) // 2, (rows - h) // 2
        grid = []
        for y in range(rows):
            row_cells = []
            for x in range(cols):
                if offx <= x < offx + w and offy <= y < offy + h:
                    r, g, b = px[x - offx, y - offy]
                    if use_color:
                        idx = self._nearest((r, g, b), palette)
                        char = "█"
                    else:
                        lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
                        idx = None
                        char = _ASCII_RAMP[min(len(_ASCII_RAMP) - 1,
                                             int(lum * len(_ASCII_RAMP)))]
                else:
                    idx, char = None, " "
                row_cells.append((idx, char))
            grid.append(row_cells)
        return grid


# --------------------------------------------------------------------------
# Playback engine (mpg123 --remote subprocess)
# --------------------------------------------------------------------------

class Engine:
    """Controls one `mpg123 --remote` subprocess via its stdin/stdout."""

    STOPPED, PAUSED, PLAYING = 0, 1, 2

    def __init__(self, audio_device: str | None = None):
        cmd = ["mpg123", "--remote", "--quiet"]
        if audio_device:
            cmd += ["-o", audio_device]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        os.set_blocking(self.proc.stdout.fileno(), False)
        self._buf = ""
        self.state = self.STOPPED
        self.position = 0.0   # seconds into current track
        self.length = 0.0     # seconds, from @F (sec + sec_left)
        self.ended = False    # set True when a track plays to its end

    # -- commands ------------------------------------------------------
    def _send(self, cmd: str) -> None:
        try:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    def load(self, path: str) -> None:
        self.position = 0.0
        self.length = 0.0
        self.ended = False
        self.state = self.PLAYING
        self._send(f"LOAD {path}")

    def pause_toggle(self) -> None:
        if self.state == self.STOPPED:
            return
        self._send("PAUSE")

    def stop(self) -> None:
        self.state = self.STOPPED
        self.position = 0.0
        self._send("STOP")

    def seek(self, delta_seconds: int) -> None:
        if self.state == self.STOPPED:
            return
        sign = "+" if delta_seconds >= 0 else "-"
        self._send(f"JUMP {sign}{abs(delta_seconds)}s")

    def set_volume(self, percent: float) -> None:
        self._send(f"VOLUME {percent:.1f}")

    def quit(self) -> None:
        try:
            self._send("QUIT")
        finally:
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    # -- responses -----------------------------------------------------
    def poll(self) -> None:
        """Drain available stdout lines, updating state (non-blocking)."""
        fd = self.proc.stdout.fileno()
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            try:
                chunk = os.read(fd, 4096).decode("utf-8", "replace")
            except (OSError, ValueError):
                break
            if not chunk:
                break
            self._buf += chunk
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                self._handle_line(line.strip())

    def _handle_line(self, line: str) -> None:
        if line.startswith("@F "):
            # @F <frame> <frames_left> <sec> <sec_left>
            try:
                _, _, _, sec, sec_left = line.split()[:5]
                self.position = float(sec)
                self.length = float(sec) + float(sec_left)
            except (ValueError, IndexError):
                pass
        elif line.startswith("@P "):
            try:
                code = int(line.split()[1])
            except (ValueError, IndexError):
                return
            if code == 0 and self.state == self.PLAYING:
                # natural end of track (STOP sets state first, so it
                # never lands here)
                self.state = self.STOPPED
                self.ended = True
            elif code == 1:
                self.state = self.PAUSED
            elif code == 2:
                self.state = self.PLAYING
            # code 3 ("decoder drained at EOF") is deliberately ignored:
            # it always precedes the final @P 0, and leaving the state
            # untouched lets that @P 0 register as a natural track end.
        # @R (banner), @I (id3), @E (errors) etc. are intentionally ignored


# --------------------------------------------------------------------------
# Queue logic (pure, UI-independent)
# --------------------------------------------------------------------------

@dataclass
class Queue:
    n: int
    order: list = field(default_factory=list)
    pos: int = 0            # position inside order
    shuffle: bool = False
    repeat: str = "off"     # off | all | one

    def __post_init__(self):
        self.order = list(range(self.n))

    @property
    def current(self) -> int | None:
        if not self.order:
            return None
        return self.order[self.pos]

    def play_index(self, i: int) -> None:
        """Jump playback to track i, keeping it first if shuffling."""
        if self.shuffle:
            rest = [x for x in range(self.n) if x != i]
            random.shuffle(rest)
            self.order = [i] + rest
        else:
            self.order = list(range(self.n))
        self.pos = self.order.index(i)

    def toggle_shuffle(self) -> None:
        cur = self.current
        self.shuffle = not self.shuffle
        if self.shuffle and cur is not None:
            rest = [x for x in range(self.n) if x != cur]
            random.shuffle(rest)
            self.order = [cur] + rest
            self.pos = 0
        else:
            self.order = list(range(self.n))
            self.pos = cur if cur is not None else 0

    def cycle_repeat(self) -> None:
        self.repeat = {"off": "all", "all": "one", "one": "off"}[self.repeat]

    def advance(self, direction: int) -> int | None:
        """Move to next (+1) / prev (-1) track. Returns track index or None."""
        if not self.order:
            return None
        if direction > 0 and self.repeat == "one":
            return self.current
        nxt = self.pos + direction
        if nxt >= len(self.order):
            if self.repeat == "all":
                nxt = 0
                if self.shuffle:  # reshuffle each loop, keep playing forward
                    cur = self.current
                    rest = [x for x in range(self.n) if x != cur]
                    random.shuffle(rest)
                    self.order = [cur] + rest
                    self.pos = 0
                    return self.advance(+1)
            else:
                return None  # stop at the end
        elif nxt < 0:
            nxt = 0 if self.repeat == "off" else len(self.order) - 1
        self.pos = nxt
        return self.current


# --------------------------------------------------------------------------
# Curses UI
# --------------------------------------------------------------------------

KEY_HINTS = ("↑↓/jk select · Enter play · Space pause · n/p next/prev · "
             "←/→ seek · +/- vol · s shuffle · r repeat · a art · q quit")

REPEAT_LABEL = {"off": "off", "all": "all", "one": "one"}


def compute_layout(h: int, w: int, art_on: bool) -> dict:
    """Pure layout logic; returns panel/list geometry for a terminal size."""
    layout = {
        "panel_w": 0, "list_w": max(0, w - 1), "art_h": 0,
    }
    if art_on and h >= 14 and w >= 76 and h - 5 >= 7:
        panel_w = max(24, min(40, w // 3))
        list_w = w - 1 - panel_w
        if list_w >= 26:
            layout["panel_w"] = panel_w
            layout["list_w"] = list_w
    if layout["panel_w"]:
        layout["art_h"] = h - 5
    return layout


def _draw_run(s, y, x, cells, color_pairs) -> int:
    """Draw a row of (color_index|None, char) cells at (y, x)."""
    i = 0
    n = len(cells)
    while i < n:
        col, ch = cells[i]
        j = i + 1
        while j < n and cells[j][0] == col:
            j += 1
        text = "".join(c[1] for c in cells[i:j])
        if col is not None:
            s.addstr(y, x + i, text, color_pairs[col])
        else:
            s.addstr(y, x + i, text)
        i = j
    return x + n


class UI:
    def __init__(self, stdscr, tracks: list, directory: str,
                 engine=None):
        self.stdscr = stdscr
        self.tracks = tracks
        self.directory = directory
        self.queue = Queue(len(tracks))
        self.engine = engine if engine is not None else Engine()
        self.cursor = 0
        self.top = 0  # first visible track row
        self.volume = 70.0
        self.playing: int | None = None
        self.art_on = False  # opt-in: press `a` to pick art, nothing auto-shown
        self.images = scan_album_art(directory)
        self.cover = CoverArt(directory, self.images)
        self.message = "" if HAVE_TINYTAG else "tinytag missing: showing filenames"
        self.engine.set_volume(self.volume)

    # -- playback actions ----------------------------------------------
    def play(self, i: int) -> None:
        self.queue.play_index(i)
        self.engine.load(self.tracks[i].path)
        self.cover.set_track(self.tracks[i].path)
        self.playing = i

    def toggle_pause(self) -> None:
        if self.playing is None:
            if self.tracks:
                self.play(self.cursor)
        else:
            self.engine.pause_toggle()

    def seek(self, delta: int) -> None:
        self.engine.seek(delta)

    def step(self, direction: int) -> None:
        nxt = self.queue.advance(direction)
        if nxt is None:
            self.engine.stop()
            self.playing = None
        else:
            self.engine.load(self.tracks[nxt].path)
            self.cover.set_track(self.tracks[nxt].path)
            self.playing = nxt

    def on_track_end(self) -> None:
        self.engine.ended = False
        if self.queue.repeat == "one" and self.playing is not None:
            self.engine.load(self.tracks[self.playing].path)
        else:
            self.step(+1)

    # -- rendering ------------------------------------------------------
    def draw(self) -> None:
        s = self.stdscr
        h, w = s.getmaxyx()
        s.erase()
        if h < 8 or w < 40:
            s.addstr(0, 0, "terminal too small"[:w - 1])
            s.refresh()
            return

        use_color = curses.has_colors()
        header = f" sonic  ·  {self.directory} "
        s.addstr(0, 0, header[:w - 1], curses.A_BOLD | self._color(1))

        layout = compute_layout(h, w, self.art_on)
        list_w = layout["list_w"]
        list_h = h - 5
        panel_w = layout["panel_w"]

        if self.cursor < self.top:
            self.top = self.cursor
        if self.cursor >= self.top + list_h:
            self.top = self.cursor - list_h + 1
        num_w = len(str(len(self.tracks)))
        for row in range(list_h):
            i = self.top + row
            if i >= len(self.tracks):
                break
            t = self.tracks[i]
            marker = "▶" if i == self.playing else " "
            dur = format_time(t.duration) if t.duration else "--:--"
            line = f"{marker} {i + 1:>{num_w}}. {t.display}  {dur}"
            attr = curses.A_REVERSE if i == self.cursor else curses.A_NORMAL
            if i == self.playing and i != self.cursor:
                attr |= self._color(2) if use_color else curses.A_BOLD
            s.addstr(1 + row, 0, line[:list_w], attr)

        if panel_w:
            self._draw_panel(h, w, layout, use_color)

        if self.playing is not None:
            t = self.tracks[self.playing]
            state = "⏸" if self.engine.state == Engine.PAUSED else "▶"
            s.addstr(h - 4, 0, f" {state} {t.display}  {self._cover_label()}"[:w - 1],
                     curses.A_BOLD | self._color(2))
            total = t.duration or self.engine.length or 1.0
            pos = min(self.engine.position, total)
            bar_w = max(10, w - 24)
            bar = progress_bar(pos / total, bar_w)
            s.addstr(h - 3, 0,
                     f" [{bar}] {format_time(pos)}/{format_time(total)}"[:w - 1],
                     self._color(3))
        else:
            s.addstr(h - 4, 0, " ■ stopped"[:w - 1], curses.A_DIM)
            s.addstr(h - 3, 0, "")

        status = (f" vol {int(self.volume)}%  "
                  f"[shuffle {'on' if self.queue.shuffle else 'off'}]  "
                  f"[repeat {REPEAT_LABEL[self.queue.repeat]}]  "
                  f"[art {'on' if self.art_on else 'off'}]")
        if not panel_w and self.art_on:
            status += "  ·  panel hidden: terminal too small"
        if self.message:
            status += f"  ·  {self.message}"
        s.addstr(h - 2, 0, status[:w - 1], curses.A_DIM)
        s.addstr(h - 1, 0, KEY_HINTS[:w - 1], curses.A_DIM)
        s.refresh()

    def _cover_label(self) -> str:
        if not self.art_on:
            return "[art off]"
        if not self.cover.available:
            return "[art: Pillow missing]"
        if self.cover.manual == EMBEDDED_CHOICE:
            return "[◉ embedded cover]" if self.cover._embedded is not None else "[no embedded cover]"
        if self.cover.path:
            return f"[◉ {os.path.basename(self.cover.path)}]"
        return "[no cover]"

    def _draw_panel(self, h: int, w: int, layout: dict, use_color: bool) -> None:
        s = self.stdscr
        panel_w = layout["panel_w"]
        panel_x = w - 1 - panel_w
        ncolors = curses.COLORS if use_color else 0
        sep = "│" if use_color else "|"
        for y in range(1, h - 4):
            s.addstr(y, panel_x, sep, curses.A_DIM)

        art_x = panel_x + 2
        art_w = max(1, panel_w - 3)

        if layout["art_h"] and self.art_on:
            art_y = 1
            cells = self.cover.render(art_w, layout["art_h"], use_color, ncolors)
            if cells is None:
                if not self.cover.available:
                    msg = "install Pillow for art"
                elif self.cover.manual == EMBEDDED_CHOICE:
                    msg = "no embedded cover"
                else:
                    msg = "no album art"
                s.addstr(art_y, art_x, msg[:art_w], curses.A_DIM)
            else:
                pair_map = {}
                if use_color:
                    pair_map = self._palette_pairs(ncolors)
                for i, row in enumerate(cells[:layout["art_h"]]):
                    _draw_run(s, art_y + i, art_x, row, pair_map)

    def _palette_pairs(self, ncolors: int) -> dict:
        if not hasattr(self, "__palette"):
            self.__palette = {}
            for idx, _ in terminal_palette(ncolors):
                if idx not in self.__palette:
                    self.__palette[idx] = curses.color_pair(idx + 1)
        return self.__palette

    def _color(self, n: int) -> int:
        return curses.color_pair(n) if curses.has_colors() else curses.A_NORMAL

    # -- art picker -----------------------------------------------------
    def _ref_track_path(self) -> str | None:
        if self.playing is not None and 0 <= self.playing < len(self.tracks):
            return self.tracks[self.playing].path
        if 0 <= self.cursor < len(self.tracks):
            return self.tracks[self.cursor].path
        return None

    def _enable_art_via_picker(self) -> None:
        """Turn art on after the user picks which image to use."""
        if not HAVE_PIL:
            self.message = "art: install Pillow for album art (pip install Pillow)"
            return
        self.images = scan_album_art(self.directory)
        self.cover.refresh_images(self.images)
        ref = self._ref_track_path()
        has_embedded = get_embedded_image(ref) is not None if ref else False
        choices = build_art_choices(self.images, has_embedded)
        if not choices:
            self.message = "no album art found (no images, no embedded cover)"
            return
        initial = 0
        if self.cover.manual in choices:
            initial = choices.index(self.cover.manual)
        elif ref:
            auto = find_cover(ref, self.images)
            if auto in choices:
                initial = choices.index(auto)
            elif has_embedded:
                initial = choices.index(EMBEDDED_CHOICE)
        sel = self._prompt_choice(choices, initial)
        if sel is None:
            return  # cancelled: stay off
        self.cover.set_manual(sel)
        if ref:
            self.cover.set_track(ref)
        elif self.playing is not None:
            self.cover.set_track(self.tracks[self.playing].path)
        self.art_on = True
        self.message = ""

    def _prompt_choice(self, choices: list, initial: int = 0) -> str | None:
        """Modal picker: ↑↓/jk + Enter to choose, Esc/q to cancel."""
        s = self.stdscr
        idx = max(0, min(initial, len(choices) - 1))
        while True:
            h, w = s.getmaxyx()
            s.erase()
            title = " Select album art  (Enter: use · Esc: cancel) "
            s.addstr(0, 0, title[:w - 1], curses.A_BOLD | self._color(1))
            max_rows = max(1, h - 3)
            if idx < 0:
                idx = 0
            if idx >= len(choices):
                idx = len(choices) - 1
            top = max(0, min(idx - max_rows // 2, max(0, len(choices) - max_rows)))
            for row in range(min(max_rows, len(choices) - top)):
                i = top + row
                label = f" {choice_label(choices[i])}"
                attr = curses.A_REVERSE if i == idx else curses.A_NORMAL
                try:
                    s.addstr(1 + row, 0, label[:w - 1], attr)
                except curses.error:
                    pass
            hint = "↑↓/jk move · Enter select · Esc cancel"
            try:
                s.addstr(h - 1, 0, hint[:w - 1], curses.A_DIM)
            except curses.error:
                pass
            s.refresh()
            try:
                key = s.getch()
            except curses.error:
                key = -1
            if key in (curses.KEY_UP, ord("k")):
                idx = max(0, idx - 1)
            elif key in (curses.KEY_DOWN, ord("j")):
                idx = min(len(choices) - 1, idx + 1)
            elif key in (curses.KEY_ENTER, 10, 13):
                return choices[idx]
            elif key in (27, ord("q")):
                return None

    # -- main loop ------------------------------------------------------
    def run(self) -> None:
        s = self.stdscr
        curses.curs_set(0)
        s.nodelay(True)
        s.keypad(True)
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)
            curses.init_pair(2, curses.COLOR_GREEN, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_RED, -1)
            for idx, _ in terminal_palette(curses.COLORS):
                try:
                    curses.init_pair(idx + 1, idx, -1)
                except curses.error:
                    break
        while True:
            self.engine.poll()
            if self.engine.ended:
                self.on_track_end()
            self.draw()
            try:
                key = s.getch()
            except curses.error:
                key = -1
            if key == -1:
                time.sleep(POLL_INTERVAL)
                continue
            if not self.handle_key(key):
                break

    def handle_key(self, key: int) -> bool:
        """Returns False when the app should quit."""
        if key in (curses.KEY_UP, ord("k")):
            self.cursor = max(0, self.cursor - 1)
        elif key in (curses.KEY_DOWN, ord("j")):
            self.cursor = min(len(self.tracks) - 1, self.cursor + 1)
        elif key in (curses.KEY_ENTER, 10, 13):
            self.play(self.cursor)
        elif key == ord(" "):
            self.toggle_pause()
        elif key == ord("n"):
            if self.playing is None:
                self.play(self.cursor)
            else:
                self.step(+1)
        elif key == ord("p"):
            if self.playing is None:
                self.play(self.cursor)
            else:
                self.step(-1)
        elif key == curses.KEY_LEFT:
            self.seek(-SEEK_STEP)
        elif key == curses.KEY_RIGHT:
            self.seek(+SEEK_STEP)
        elif key in (ord("+"), ord("=")):
            self.volume = min(100.0, self.volume + VOLUME_STEP)
            self.engine.set_volume(self.volume)
        elif key in (ord("-"), ord("_")):
            self.volume = max(0.0, self.volume - VOLUME_STEP)
            self.engine.set_volume(self.volume)
        elif key == ord("s"):
            self.queue.toggle_shuffle()
        elif key == ord("r"):
            self.queue.cycle_repeat()
        elif key == ord("a"):
            if self.art_on:
                self.art_on = False
            else:
                self._enable_art_via_picker()
        elif key in (ord("q"), 27):  # q or Esc
            return False
        return True


def run_ui(stdscr, tracks: list, directory: str) -> None:
    ui = UI(stdscr, tracks, directory)
    try:
        ui.run()
    finally:
        ui.engine.quit()


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sonic",
        description="Play the .mp3 files in the current directory.")
    parser.add_argument("-V", "--version", action="version",
                        version=f"%(prog)s {VERSION}")
    parser.parse_args(argv)

    if shutil.which("mpg123") is None:
        print("sonic: error: 'mpg123' not found on PATH "
              "(install it with your package manager).", file=sys.stderr)
        return 1

    if not sys.stdout.isatty():
        print("sonic: error: not a terminal "
              "(run it interactively in a folder with .mp3 files).",
              file=sys.stderr)
        return 1

    directory = os.getcwd()
    try:
        tracks = scan_tracks(directory)
    except OSError as e:
        print(f"sonic: error: cannot read directory: {e}", file=sys.stderr)
        return 1
    if not tracks:
        print(f"sonic: no .mp3 files in {directory}", file=sys.stderr)
        return 1

    # curses.wrapper restores the terminal on any exception, and run_ui's
    # finally-block always shuts the mpg123 child down (no orphans).
    try:
        curses.wrapper(run_ui, tracks, directory)
    except curses.error as e:
        print(f"sonic: error: terminal problem: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
