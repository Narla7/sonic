# 🎵 sonic

**A minimal CLI-only MP3 player.** `cd` into any folder full of `.mp3`
files, type `sonic`, and play them — no GUI, no daemon, no config files,
no playlists.

![version](https://img.shields.io/badge/version-0.1.0-blue) ![python](https://img.shields.io/badge/python-3.10%2B-blue) ![license](https://img.shields.io/badge/license-MIT-green) ![backend](https://img.shields.io/badge/backend-mpg123%20--remote-orange)

```sh
cd ~/Music && sonic
```

> **Version:** 0.1.0 · **Language:** Python ≥ 3.10 · **License:** MIT (c) 2026 Narla7 · **Repo:** https://github.com/Narla7/sonic
>
> Zero mandatory Python dependencies. The only hard requirement is `mpg123`
> on `PATH`, which does all decoding and audio output.

---

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Install](#install)
- [Usage](#usage)
- [CLI Reference](#cli-reference)
- [Key Bindings](#key-bindings)
- [Behavior Details](#behavior-details)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [Changelog](#changelog)
- [FAQ](#faq)
- [License](#license)

---

## Features

- 📂 **Plays the current directory** — every `*.mp3` / `*.MP3` file directly
  inside the folder you launch it from. No playlists, no library scan, no
  recursion into subdirectories.
- 🔢 **Natural sorting** — `2.mp3` comes before `10.mp3`, because the sort
  key splits filenames into digit/non-digit runs and compares numbers
  numerically.
- 🏷️ **ID3 tags** — shows `Artist - Title` and real durations when `tinytag`
  is installed; falls back to filenames (`01 - rain.mp3`) and `--:--` when it
  isn't. One corrupt tag never breaks the list.
- ⏯️ **Full transport** — play, pause, next/previous, ±5 s seek, volume in
  5 % steps (starts at 70 %).
- 🔀 **Shuffle** — random order with **no immediate repeats**; the currently
  playing track stays first when you toggle it on, and repeat-`all` re-rolls
  the order on every loop.
- 🔁 **Repeat** — cycles `off → all → one` with one keystroke.
- 📊 **Live seek bar** — elapsed/total time and progress bar, redrawn at a
  50 ms tick (~20 fps).
- 🧹 **No orphans, no mess** — quitting (`q` / `Esc` / Ctrl-C) always sends
  `QUIT` to the decoder (with a `kill` fallback after 2 s) and restores your
  terminal via `curses.wrapper`. Nothing is ever written to disk.
- 🖼️ **Album art (opt-in)** — off by default, nothing auto-shown on
  startup. Press `a` to open a picker listing every image in the folder
  plus `Embedded cover (from MP3 tags)` when the current track has one;
  `Enter` selects, `Esc` cancels. The file choice sticks for the session,
  the embedded choice reloads per track. Requires `Pillow`. Inside Kitty
  the image renders full-resolution via the Kitty graphics protocol;
  other terminals get half-block (`▀`) rendering.
- 🎨 **Color** — cyan header, green now-playing row, yellow progress bar when
  the terminal supports color (degraded to bold/dim otherwise).

Rendered screen (layout follows `UI.draw`; track data is illustrative):

```
┌──────────────────────────────────────────────────────────────┐
│ sonic  ·  /home/narla/Music                                  │
│                                                              │
│   1. TestArtist - Marathon                         20:00   │
│ ▶ 2. TestArtist - Alpha                            0:06    │
│   3. TestArtist - Beta                              0:08   │
│   4. Other - Gamma                                  0:05   │
│                                                              │
│ ▶ TestArtist - Alpha                                         │
│ [##################----------------------------------] 0:02/…
│ vol 70%  [shuffle off]  [repeat off]  ·  tinytag missing: …
│ ↑↓/jk select · Enter play · Space pause · n/p next/prev · …
└──────────────────────────────────────────────────────────────┘
```

---

## Requirements

| Dependency | Required? | Minimum | Why | Check |
|---|---|---|---|---|
| Python | ✅ yes | **3.10+** | code uses `X \| None` union annotations | `python3 --version` |
| `mpg123` (native binary) | ✅ yes | any recent | decodes MPEG audio, talks to ALSA/PulseAudio/PipeWire, drives the seek bar via `--remote` | `which mpg123` |
| `tinytag` (Python lib) | ❌ optional | ≥ 1.10 (per `requirements.txt`) | ID3 `artist`/`title`/`duration` display; graceful filename fallback when absent | `python3 -c "import tinytag"` |
| `Pillow` (Python lib) | ✅ yes | ≥ 10 (per `requirements.txt`) | album-art rendering; without it the picker refuses with `art: install Pillow for album art` | `python3 -c "import PIL"` |
| `curses` (stdlib) | ✅ yes | ships with Python | full-screen TUI; needs a real TTY | — |
| Terminal | ✅ yes | ≥ 40×8 (code minimum); **80×24 recommended** | below 40×8 the UI prints `terminal too small` and waits | `stty size` |

Two hard runtime checks, in order, before the TUI ever opens:

```sh
python3 --version   # want 3.10+ (tested on 3.14)
which mpg123        # want a path, e.g. /usr/bin/mpg123
```

`sonic` deliberately does **not** decode MP3s itself. Decoding, output to
ALSA/PulseAudio/PipeWire, and gapless-ish playback are delegated to
`mpg123`, which has done that job for over 25 years. All the TUI ever does is
push `LOAD`/`PAUSE`/`STOP`/`JUMP`/`VOLUME`/`QUIT` lines at it and read back
`@F`/`@P` status lines.

---

## Install

### 1. Prerequisite: `mpg123`

```sh
# Debian / Ubuntu / Pop!_OS / Mint
sudo apt install mpg123

# Fedora / RHEL / Rocky / AlmaLinux
sudo dnf install mpg123

# Arch / Manjaro / Omarchy
sudo pacman -S mpg123

# openSUSE
sudo zypper install mpg123
```

### 2. Get the code

```sh
git clone https://github.com/Narla7/sonic.git
cd sonic
```

### 3. Python dependencies

```sh
pip install -r requirements.txt        # installs tinytag>=1.10, Pillow>=10
```

`tinytag` is optional — without it, rows show filenames instead of
`Artist - Title`, durations show `--:--`, and the status bar notes
`tinytag missing: showing filenames`. `Pillow` is required for album
art — without it, pressing `a` reports
`art: install Pillow for album art` and no art is shown. If your
distro's Python is externally-managed (PEP 668) and `pip` refuses, any
of these work too:

- System package: `sudo apt install python3-tinytag` (Debian/Ubuntu),
  `python-tinytag` from the AUR (Arch) — or check your distro for a tinytag
  package.
- User install: `pip install --user tinytag`
- Tool-managed: `uv pip install --system tinytag`
- A venv: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`

### 4. Put `sonic` on your PATH

```sh
chmod +x sonic.py
ln -s "$PWD/sonic.py" ~/.local/bin/sonic
```

### 5. Verify

```sh
which sonic        # expect ~/.local/bin/sonic
sonic --version    # expect: sonic 0.1.0
sonic --help       # expect: usage line, no error
```

`~/.local/bin` is on `PATH` by default on most distros. If `which sonic`
finds nothing, append to your `~/.bashrc` (or `~/.zshrc`) and reopen the
terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

---

## Usage

```sh
cd ~/Music            # any folder with .mp3 files directly inside it
sonic
```

That's it. `sonic` scans the **current directory only** (no subfolders),
opens the track list, and waits. Press `Enter` on a track (or `Space`, which
plays the selection when nothing is playing) to start.

Variants of the same call:

```sh
cd ~/Music/dnb && sonic                     # play that album folder
python3 "$HOME/.local/bin/sonic"            # run directly, no symlink
sonic --help                                # usage text, works in a pipe
sonic --version                             # "sonic 0.1.0", works in a pipe
```

Exit with `q` (or `Esc`, or Ctrl-C) — the decoder is always stopped and the
terminal is always restored. `--help` and `--version` are the only two
invocations that work non-interactively; everything else requires a real
TTY on stdout.

---

## CLI Reference

`usage: sonic [-h] [-V]`

| Argument | Default | Description |
|---|---|---|
| `-h`, `--help` | — | print usage and exit `0` |
| `-V`, `--version` | — | print `sonic 0.1.0` and exit `0` |
| *(positional)* | none | none accepted; `argparse` errors on extras |

### Exit codes

| Code | When |
|---|---|
| `0` | clean quit (`q` / `Esc` / Ctrl-C), `--help`, or `--version` |
| `1` | `mpg123` missing on `PATH`, stdout is not a TTY, directory unreadable, no `.mp3` files found, or a `curses` terminal error |

Every error path writes a single `sonic:`-prefixed line to **stderr** and
returns before the TUI starts, so the terminal is never touched in those
cases.

### Internal constants

| Constant | Value | Meaning |
|---|---|---|
| `VERSION` | `0.1.0` | reported by `--version` |
| `SEEK_STEP` | `5` | seconds seeked per `←` / `→` press |
| `VOLUME_STEP` | `5` | percent per `+` / `-` press |
| `POLL_INTERVAL` | `0.05` | UI tick in seconds (≈ 20 fps) |
| default volume | `70.0` | set on the decoder once at startup, clamped to 0–100 |

---

## Key Bindings

| Key | Action |
|---|---|
| `↑` / `↓`, `j` / `k` | Move selection cursor (scrolls the list) |
| `Enter` | Play the selected track |
| `Space` | Play / pause toggle — plays the selection if stopped |
| `n` / `p` | Next / previous track (starts playing the selection if stopped) |
| `←` / `→` | Seek ∓ 5 seconds (`JUMP ±5s`) |
| `+` / `=`, `-` / `_` | Volume up / down, 5 % steps (`VOLUME <pct>`), clamped 0–100 |
| `s` | Shuffle on / off |
| `r` | Repeat `off → all → one` |
| `a` | Album art off → picker (choose image, art on) → off |
| `q` / `Esc` | Quit |

Notes, straight from `handle_key`:

- `n` / `p` while **stopped** start playback from the cursor (`play()`),
  they don't move the selection.
- `Enter` is matched as `KEY_ENTER`, `10`, or `13`; `Esc` is ASCII `27`.
- `+` on many keyboards requires Shift; `=` is accepted so you don't miss it.
- All other keys are silently ignored — mashing the keyboard cannot crash
  the loop, and every unmapped key call still redraws.

### Boundary behavior (from `Queue.advance`)

| Situation | repeat `off` | repeat `all` | repeat `one` |
|---|---|---|---|
| Track ends naturally | advance; **stop** after the last track | wrap to first; re-shuffle order if shuffle is on | replay the same track |
| `n` on the last track | **stop** (playback ends) | wrap to first | replay the current track |
| `p` on the first track | clamp to first | wrap to last | wrap to last |

Shuffle and wrap are orthogonal: with repeat `all` + shuffle on, each wrap
re-rolls the order behind the current track, so the gap between repeats
changes every loop. With repeat `one`, `p` is *not* clamped to the current
track — only forward advance repeats — because the guard in `advance` checks
`direction > 0`.

---

## Behavior Details

- **Scope.** `os.listdir` + `name.lower().endswith(".mp3")` +
  `os.path.isfile`. Subdirectories are excluded by the `isfile` check;
  symlinks to regular files are treated as files, so symlinked MP3s play.
- **Order.** Natural sort: `re.split(r"(\d+)")` then numeric vs.
  `lower()` comparison. `2.mp3` < `10.mp3`; `Album b` < `Album B` (ties are
  stable, so it's effectively case-insensitive).
- **Display.** Row = `▶ <n>. <display>  <dur>` where `display` is
  `Artist - Title` when an artist tag exists, else the title, else the
  filename minus extension. Durations are `m:ss` from tags, or `--:--`.
  The now-playing row shows `▶`/`⏸` from engine state; when nothing is
  playing the footer shows `■ stopped` in dim.
- **Volume.** Starts at `70.0` on every launch (set via `VOLUME 70.0` at UI
  init), changes apply instantly, `0` effectively mutes. Not persisted.
- **Pause.** `PAUSE` is a toggle sent to mpg123; state follows `@P 1`/`@P 2`.
  Pausing or seeking while stopped is a silent no-op (engine guards on
  state).
- **Seek.** `JUMP +5s` / `JUMP -5s`; position and length are read back from
  the `@F` line (`position = sec`, `length = sec + sec_left`). The progress
  bar prefers the tag duration as total when tinytag provided one, falling
  back to the decoder-derived length, then `1.0` as a placeholder.
- **Progress bar.** `#` filled / `-` empty, width `max(10, w-24)`, fraction
  clamped 0–1. Header/list/status/hints are truncated to `w-1` so a
  terminal resize can never throw `curses` errors.
- **Album art.** Off at startup (`art_on = False`). `a` while off opens a
  modal picker (`↑↓`/`jk` + `Enter`, `Esc` cancels) over the folder's
  images (any extension in `IMAGE_EXTS`: jpg/jpeg/jfif/png/webp/bmp/gif/
  tif/tiff/avif) plus the embedded cover when `tinytag` finds one in the
  current track's tags. `a` while on just turns it off. Needs `Pillow`;
  corrupt/unreadable images fall back to `no album art` instead of
  crashing. The side panel needs ≥ 76×14, else the status bar notes
  `panel hidden: terminal too small`.
- **Resize / small terminals.** Below 40×8 the screen shows
  `terminal too small` and keeps polling — resize and it reappears.
- **Missing/corrupt tags.** `TinyTag.get()` is wrapped in `try/except`; any
  parse failure falls back to the filename. One bad apple never breaks the
  list, and the app never crashes mid-scan.
- **Empty directory / no MP3s.** `sonic: no .mp3 files in <dir>` on stderr,
  exit `1`, terminal untouched.

---

## How It Works

```
┌─────────────┐  keypresses   ┌──────────────┐  stdin commands   ┌──────────┐
│  curses TUI │ ────────────▶ │    Engine    │ ─────────────────▶ │ mpg123   │
│  (UI class) │ ◀──────────── │  (subprocess │ ◀───────────────── │ --remote │
│ ~20 fps tick│  state/pos    │    wrapper)  │  @F / @P lines    │  child   │
└─────────────┘               └──────────────┘                   └──────────┘
```

All four components live in the single 524-line file `sonic.py` (stdlib +
optional `tinytag`).

### 1. Scanner — `scan_tracks()` / `Track`

Lists the working directory, keeps `*.mp3`/`*.MP3` regular files
(case-insensitive extension), natural-sorts them, then — when `tinytag`
imports successfully — reads `title`/`artist`/`duration` per file inside a
`try/except`. Produces a `Track(path, title, artist, duration)` list;
`HAVE_TINYTAG` is decided once at import time.

### 2. Engine — `Engine` (mpg123 `--remote` wrapper)

Spawns `mpg123 --remote --quiet` **once** at startup (stderr → `/dev/null`,
line-buffered pipes, stdout set non-blocking) and drives it for the whole
session:

- **Commands sent:** `LOAD <path>`, `PAUSE` (toggle), `STOP`,
  `JUMP ±<n>s`, `VOLUME <pct>` (one decimal), `QUIT`.
- **Responses parsed** in a non-blocking `poll()` drained every tick:
  - `@F <frame> <left> <sec> <sec_left>` → position / length for the seek bar
  - `@P 0|1|2` → stopped / paused / playing
  - `@P 3` → **deliberately ignored** (see below)
  - `@R` (banner), `@I` (id3), `@E` (errors) → ignored on purpose

Next/previous/shuffle/repeat are implemented **client-side** as `LOAD` of
the next file — no mpg123 playlist features involved, so the order logic is
ours to reason about and test.

**The `@P 3` subtlety.** mpg123 emits an undocumented `@P 3` ("decoder
drained at EOF") immediately before the final `@P 0` when a track ends
naturally. If the engine treated `3` as a state ("ended"), the following
`@P 0` would be ignored (state no longer `PLAYING`) and auto-advance would
die. So `_handle_line` matches only `0`, `1`, `2` — a natural end is `@P 0`
arriving while the engine still believes it is `PLAYING` (a manual `STOP`
sets state `STOPPED` first and never lands there). This single rule powers
`on_track_end()` → repeat-`one` replay or `step(+1)`.

### 3. Queue — `Queue` (pure order logic)

A dataclass holding `order` (list of track indices), `pos`, `shuffle`, and
`repeat`. All methods are UI-independent and side-effect-free:

- `play_index(i)` — jump to track `i`; when shuffling, `[i] + shuffled rest`
  so the picked track plays first and never immediately repeats.
- `toggle_shuffle()` — on: current track stays first, rest shuffled; off:
  restore strict sequential order at the current track.
- `cycle_repeat()` — `off → all → one → off`.
- `advance(±1)` — the boundary matrix above, including the repeat-`all`
  shuffle re-roll that keeps the current track first and recurses into a
  forward step.

### 4. TUI — `UI` (curses render loop)

`curses.wrapper(run_ui, ...)` initializes the terminal and guarantees
restoration on every exit path. `UI.run()` is a tight loop: `engine.poll()`
→ handle natural track end → `draw()` → non-blocking `getch()` (50 ms
`time.sleep` when idle). Layout is fixed rows — header `0`, track list
(`h-5` rows with cursor-following scroll), now-playing `h-4`, progress
`h-3`, status `h-2`, key hints `h-1` — with optional color pairs
(cyan/green/yellow via `use_default_colors`).

### Shutdown, twice guaranteed

`run_ui`'s `finally` block calls `engine.quit()` (send `QUIT`, then
`proc.wait(timeout=2)`, then `proc.kill()` if it times out), and
`curses.wrapper` restores the terminal even when Ctrl-C interrupts the
rendering loop (`KeyboardInterrupt` is caught in `main` and exits `0`).
No zombie decoders, no garbled terminals.

---

## Project Structure

```
sonic/
├── sonic.py          # the entire player — executable, #!/usr/bin/env python3,
│                     # 524 lines: scanner + engine + queue + curses UI
├── requirements.txt  # tinytag>=1.10 — optional ID3 support only
├── LICENSE           # MIT, (c) 2026 Narla7
└── README.md         # you are here
```

No `pyproject.toml`, no `__init__.py`, no tests directory, no CI config —
by design. The install is a symlink, and the app writes nothing at runtime.

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `sonic: error: 'mpg123' not found on PATH (install it with your package manager.)` | `mpg123` is missing → install it (see [Requirements](#requirements)); exit `1` |
| `sonic: error: not a terminal (run it interactively in a folder with .mp3 files.)` | stdout is piped/redirected (`sonic \| less`) — `sonic` needs a real TTY; exit `1` |
| `sonic: no .mp3 files in <dir>` | Wrong folder, or files are `.m4a`/`.flac`/`.ogg` (unsupported — convert with `ffmpeg`, or symlink real `.mp3`s); exit `1` |
| `sonic: error: cannot read directory: …` | Working directory unreadable (permissions); exit `1` |
| `sonic: error: terminal problem: …` | `curses` failure — run inside a terminal with a valid `TERM` (try `TERM=xterm-256color`); exit `1` |
| Screen shows `terminal too small` | Terminal smaller than 40×8 — resize; 80×24 is the comfortable floor |
| Filenames instead of `Artist - Title`, durations `--:--` | `tinytag` not installed → `pip install -r requirements.txt`; status bar says `tinytag missing` |
| `a` says `art: install Pillow for album art` / `no album art found` | `Pillow` missing → `pip install -r requirements.txt`; or the folder has no images and the track has no embedded cover |
| No sound but the UI still moves | Audio server issue outside `sonic`: check `alsamixer`/`pavucontrol`, and that `mpg123 somefile.mp3` alone makes noise |
| Leftover `mpg123 --remote` process | Shouldn't happen (graceful `QUIT` + 2 s `kill` fallback) — `pkill -f 'mpg123 --remote'` cleans up manually |
| `-V` works but plain `sonic` errors | Run it in a folder containing at least one `.mp3` — that's the whole prereq besides the TTY |

---

## Uninstall

```sh
rm ~/.local/bin/sonic                 # remove the symlink
rm -rf ~/Projects/sonic               # remove the clone (or wherever you put it)
pip uninstall tinytag Pillow          # only if you want the libraries gone too
```

That's everything. `sonic` never writes config files, caches, session
state, or dotfiles anywhere, so there is nothing else to clean up.

---

## Roadmap

Ideas, roughly in order of likelihood:

- [ ] `m` mute toggle (trivial — `MUTE`/`UNMUTE` may be added to the protocol wrapper)
- [ ] `/` incremental search/filter in the track list
- [ ] `d` toggle: include subdirectories ("album mode")
- [ ] Persist volume in a tiny dotfile
- [ ] `--backend mpv` option for systems without `mpg123`
- [ ] Packaging: AUR / PyPI entry point

---

## Contributing

The project is deliberately one file — keep it that way.

1. Clone and symlink as in [Install](#install).
2. Sanity-check before you start:
   ```sh
   python3 -m py_compile sonic.py     # syntax check
   python3 sonic.py --help            # CLI check, no TTY needed
   ```
3. There is no automated test suite in the repo. Test by hand in a scratch
   directory with a handful of MP3s (e.g. generated with
   `ffmpeg -f lavfi -i "sine=frequency=440:duration=3" t$i.mp3` if you have
   ffmpeg). The `Queue` class is pure index math with no I/O — regression
   cases for shuffle/repeat/boundaries are easiest to reason about there.
4. Style rules observed by the code: stdlib-first, `X | None` annotations,
   module section-banner comments, ~80-column lines, no new mandatory
   dependencies, docstrings on classes and complex functions.
5. Open a PR against `main`. Keep commits small and messages descriptive
   (see git history: `Initial commit: sonic v0.1.0 CLI mp3 player`).

---

## Changelog

### 0.1.0 — 2026-09-23 (initial release)

- Curses TUI listing `.mp3` files in the working directory, naturally sorted.
- `mpg123 --remote --quiet` backend: `LOAD`/`PAUSE`/`STOP`/`JUMP`/`VOLUME`/`QUIT`.
- Play/pause/next/prev, ±5 s seek, volume in 5 % steps (default 70 %).
- Shuffle (no immediate repeats, re-rolled per loop in repeat-`all`) and
  repeat `off → all → one`.
- Optional `tinytag` ID3 metadata with filename fallback.
- Graceful shutdown: `QUIT` + 2 s `kill` fallback, `curses.wrapper` restore,
  exit `0` on Ctrl-C.
- MIT LICENSE.

---

## FAQ

**Why `mpg123` and not a pure-Python decoder?**
Decoding MPEG audio correctly — including output routing to ALSA,
PulseAudio, or PipeWire — is a solved problem that nothing in Python's
stdlib touches. `mpg123` is one tiny binary, already packaged everywhere,
and its `--remote` protocol gives clean seek (frame-accurate `@F`) and
state (`@P`) feedback. sonic becomes a ~500-line state machine instead of a
decoder project.

**Why only the current directory?**
Deliberate scope. `cd ~/Music/<album>` *is* the playlist. Recursion,
filtering by genre/album, and library building are on nobody's roadmap;
they're what the roadmap's "album mode" would add — via one keypress, not a
database.

**Why does volume reset to 70 % every launch?**
The default is a code constant (`70.0`), set on the decoder at startup. It's
a sane middle ground between inaudible and 100 % (where many recordings
clip or blast). Persisting it is a listed roadmap item.

**Why MP3 only?**
`mpg123` decodes MPEG audio (MP1/MP2/MP3). FLAC/OGG/M4A support would need
a second backend; that's what the `--backend mpv` roadmap item is for.
Until then, convert or symlink.

**Does sonic write anything to disk? Do I need a config file?**
No and no. The scanner only reads; every setting (volume, shuffle, repeat)
lives in memory for the session. Uninstalling is deleting a symlink.

**Does it work over SSH / in tmux?**
Yes, provided the session has a real TTY with curses support — that's what
the `isatty` check enforces. Plain `TERM` values (`xterm-256color` etc.)
work; the UI degrades to bold/dim if the terminal has no colors.

**What's `@P 3` and why is it ignored?**
An undocumented mpg123 status meaning "decoder drained at EOF". It always
arrives right before the final `@P 0`; reacting to it would mark the track
as ended early and break auto-advance. Ignoring it lets the `@P 0` register
as a natural track end. See [How It Works](#how-it-works).

**Does it work on Windows / macOS?**
Unix-first. `curses` is not in the Windows Python stdlib; on macOS it works
but you must install `mpg123` yourself (e.g. `brew install mpg123`). Linux
is the reference platform.

**What about a key I pressed that did nothing?**
Every mapped key has one action; anything else is ignored as designed.
Volume/pause/seek while stopped are silent no-ops per engine guards.

---

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Narla7.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software") …
(standard MIT terms — you can use, copy, modify, merge, publish, and sell
copies, with the license preserved; the software is provided as-is, without
warranty).