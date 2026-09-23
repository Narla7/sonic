#!/usr/bin/env python3
"""sonic - a minimal CLI mp3 player for the current directory.

Usage:
    cd ~/Music && sonic

Requires: mpg123 on PATH. Optional: tinytag (for ID3 title/artist display).
"""

import argparse
import curses
import os
import random
import re
import select
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field

VERSION = "0.1.0"

SEEK_STEP = 5        # seconds per left/right press
VOLUME_STEP = 5      # percent per +/- press
POLL_INTERVAL = 0.05  # UI tick, seconds

try:
    from tinytag import TinyTag

    HAVE_TINYTAG = True
except ImportError:  # degrade gracefully to filenames
    HAVE_TINYTAG = False


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
             "←/→ seek · +/- vol · s shuffle · r repeat · q quit")

REPEAT_LABEL = {"off": "off", "all": "all", "one": "one"}


class UI:
    def __init__(self, stdscr, tracks: list, directory: str):
        self.stdscr = stdscr
        self.tracks = tracks
        self.directory = directory
        self.queue = Queue(len(tracks))
        self.engine = Engine()
        self.cursor = 0
        self.top = 0  # first visible track row
        self.volume = 70.0
        self.playing: int | None = None
        self.message = "" if HAVE_TINYTAG else "tinytag missing: showing filenames"
        self.engine.set_volume(self.volume)

    # -- playback actions ----------------------------------------------
    def play(self, i: int) -> None:
        self.queue.play_index(i)
        self.engine.load(self.tracks[i].path)
        self.playing = i

    def toggle_pause(self) -> None:
        if self.playing is None:
            if self.tracks:
                self.play(self.cursor)
        else:
            self.engine.pause_toggle()

    def step(self, direction: int) -> None:
        nxt = self.queue.advance(direction)
        if nxt is None:
            self.engine.stop()
            self.playing = None
        else:
            self.engine.load(self.tracks[nxt].path)
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

        list_h = h - 5
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
            s.addstr(1 + row, 0, line[:w - 1], attr)

        if self.playing is not None:
            t = self.tracks[self.playing]
            state = "⏸" if self.engine.state == Engine.PAUSED else "▶"
            s.addstr(h - 4, 0, f" {state} {t.display}"[:w - 1],
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
                  f"[repeat {REPEAT_LABEL[self.queue.repeat]}]")
        if self.message:
            status += f"  ·  {self.message}"
        s.addstr(h - 2, 0, status[:w - 1], curses.A_DIM)
        s.addstr(h - 1, 0, KEY_HINTS[:w - 1], curses.A_DIM)
        s.refresh()

    def _color(self, n: int) -> int:
        return curses.color_pair(n) if curses.has_colors() else curses.A_NORMAL

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
            self.engine.seek(-SEEK_STEP)
        elif key == curses.KEY_RIGHT:
            self.engine.seek(+SEEK_STEP)
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
