# sonic

**A minimal CLI-only MP3 player.** `cd` into any folder full of `.mp3` files,
type `sonic`, and play them — no GUI, no daemon, no config files.

```
┌──────────────────────────────────────────────────────────────┐
│ sonic  ·  /home/narla/Music                                  │
│                                                              │
│   1. TestArtist - Marathon  20:00                            │
│ ▶ 2. TestArtist - Alpha  0:06                                │
│   3. TestArtist - Beta  0:08                                 │
│   4. Other - Gamma  0:05                                     │
│                                                              │
│ ▶ TestArtist - Alpha                                         │
│ [###############-----------------------------------------]   │
│   0:02 / 0:06                                                │
│ vol 70%  [shuffle off]  [repeat: off]                        │
│ ↑↓/jk select · Enter play · Space pause · n/p next/prev · …  │
└──────────────────────────────────────────────────────────────┘
```

Unix/Linux first. Single Python file, zero mandatory dependencies beyond an
MP3 backend you almost certainly already have.

---

## Table of contents

- [Features](#features)
- [Requirements](#requirements)
- [Install](#install)
- [Usage](#usage)
- [Key bindings](#key-bindings)
- [Behavior details](#behavior-details)
- [How it works](#how-it-works)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Uninstall](#uninstall)
- [Roadmap](#roadmap)

---

## Features

- 📂 **Plays the current directory** — every `.mp3` (case-insensitive) directly
  inside the folder you launch it from. No playlists to manage, no library to
  build, no recursion into subfolders.
- 🔢 **Natural sorting** — `2.mp3` comes before `10.mp3`, like a human would
  order them.
- 🏷️ **ID3 tags** — shows `Artist - Title` and durations when `tinytag` is
  installed; falls back to filenames gracefully when it isn't.
- ⏯️ **Full transport** — play, pause, next, previous, ±5 s seek, volume.
- 🔀 **Shuffle** — random play order with no immediate repeats; the currently
  playing track stays first when you toggle it on.
- 🔁 **Repeat** — cycles `off → all → one`. In `all` mode the shuffle order is
  re-rolled every loop.
- 📊 **Live seek bar** — progress, elapsed/total time, updated ~20×/second.
- 🧹 **No orphans, no mess** — quitting (or Ctrl-C) always shuts down the
  decoder child and restores your terminal.

---

## Requirements

| Dependency | Required? | Notes |
|---|---|---|
| Python **3.10+** | ✅ yes | `sonic.py` uses `X \| None` annotations |
| `mpg123` on `PATH` | ✅ yes | does all decoding + audio output |
| `tinytag` (Python) | ❌ optional | ID3 title/artist/duration display |
| A terminal (80×24 min) | ✅ yes | uses `curses`; no GUI, no X/Wayland needed |

`sonic` deliberately does **not** decode MP3s itself — decoding, gapless-ish
output, ALSA/PulseAudio/PipeWire handling are delegated to `mpg123`, which has
done exactly that job for ~25 years.

Install `mpg123` with your distro's package manager:

```sh
# Debian / Ubuntu / Pop!_OS / Mint
sudo apt install mpg123

# Fedora / RHEL
sudo dnf install mpg123

# Arch / Manjaro / Omarchy
sudo pacman -S mpg123

# openSUSE
sudo zypper install mpg123
```

Check both prerequisites:

```sh
python3 --version   # want 3.10+
which mpg123        # want a path, e.g. /usr/bin/mpg123
```

---

## Install

### 1. Get the code

```sh
git clone https://github.com/Narla7/sonic.git
cd sonic
```

### 2. Optional: ID3 tag support

```sh
pip install -r requirements.txt
```

Without this step everything still works — track rows just show filenames
(`01 - rain.mp3`) instead of tags (`Boards of Canada - Rain`), and durations
show as `--:--`.

> On distros without `pip` (or with externally-managed Pythons), any of these
> work too: `pipx` won't help (it's a library, not an app) — use
> `uv pip install --system tinytag`, your distro's `python3-tinytag` package
> if it exists, or a venv.

### 3. Put `sonic` on your PATH

```sh
chmod +x sonic.py
ln -s "$PWD/sonic.py" ~/.local/bin/sonic
```

Verify:

```sh
which sonic        # ~/.local/bin/sonic
sonic --help
sonic --version
```

`~/.local/bin` is on `PATH` by default on most distros. If `which sonic`
finds nothing, add this to your `~/.bashrc` (or `~/.zshrc`) and reopen the
terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

---

## Usage

```sh
cd ~/Music            # any folder with .mp3 files in it
sonic
```

That's it. `sonic` scans the **current directory only** (no subfolders) and
opens the track list. Press `Enter` on a track (or `Space`) to start playing.

```sh
cd ~/Music/dnb && sonic     # play that album folder
sonic --help                # usage
sonic --version             # version
```

Exit with `q` (or `Esc`, or Ctrl-C) — the decoder is always stopped and your
terminal is always restored.

---

## Key bindings

| Key | Action |
|---|---|
| `↑` / `↓`, `j` / `k` | Move selection cursor |
| `Enter` | Play the selected track |
| `Space` | Play / pause toggle (plays selection if stopped) |
| `n` / `p` | Next / previous track |
| `←` / `→` | Seek ∓ 5 seconds |
| `+` / `=`, `-` / `_` | Volume up / down (5 % steps, starts at 70 %) |
| `s` | Shuffle on/off |
| `r` | Repeat `off → all → one` |
| `q` / `Esc` | Quit |

Notes:

- `n`/`p` while stopped start playback from the selection.
- At the top of the list, `p` clamps (repeat `off`) or wraps to the last track
  (repeat `all`/`one`).
- At the end of the list, `n` stops (repeat `off`) or wraps to the first track
  (repeat `all`); repeat `one` replays the current track.
- Unmapped keys are ignored — mashing the keyboard can't crash it.

---

## Behavior details

- **Scope:** only `*.mp3` / `*.MP3` files directly in the working directory.
  Subdirectories are ignored, symlinked files are followed (they're regular
  files as far as `os.path.isfile` cares).
- **Order:** natural sort (`2` before `10`), case-insensitive for the
  non-numeric parts.
- **Volume:** starts at 70 % every launch (set on the decoder at startup);
  changes apply instantly via `VOLUME`.
- **Shuffle:** toggling on keeps the current track playing and shuffles the
  rest behind it. With repeat `all`, the order is re-shuffled on every wrap.
- **Repeat one:** replays the same file on natural track end *and* on manual
  `n`.
- **Missing/corrupt tags:** any unreadable file or tag falls back to the
  filename — one bad apple never breaks the list.
- **No MP3s:** prints `sonic: no .mp3 files in <dir>` and exits `1` without
  touching the terminal.

---

## How it works

```
┌─────────────┐   keypresses    ┌──────────────┐   stdin commands   ┌─────────┐
│ curses TUI  │ ─────────────▶ │    Engine    │ ─────────────────▶ │ mpg123  │
│ (UI class)  │ ◀───────────── │ (subprocess  │ ◀───────────────── │--remote │
│  ~20 fps    │  state/position│  wrapper)    │  @F / @P lines    │  child  │
└─────────────┘                └──────────────┘                    └─────────┘
```

All in the single file `sonic.py` (~500 lines, stdlib + `tinytag`):

1. **Scanner** (`scan_tracks`) — globs the directory, natural-sorts, reads
   ID3 via `tinytag` when available.
2. **Engine** (`Engine`) — spawns `mpg123 --remote --quiet` once and drives it
   for the whole session over pipes:
   - commands: `LOAD <file>`, `PAUSE` (toggle), `STOP`, `JUMP ±Ns`,
     `VOLUME %`, `QUIT`
   - responses parsed: `@F <frame> <left> <sec> <sec_left>` (seek bar),
     `@P 0/1/2` (stopped/paused/playing)
   - next/previous/shuffle/repeat are implemented client-side by `LOAD`ing the
     next file — simple and race-free.
   - subtlety: `mpg123` emits an undocumented `@P 3` ("decoder drained at
     EOF") just before the final `@P 0`; the engine deliberately ignores it so
     the `@P 0` still registers as a natural track end (this powers
     auto-advance).
3. **Queue** (`Queue`) — pure play-order logic (sequential/shuffled index list
   + repeat mode), UI-independent and unit-tested.
4. **TUI** (`UI`) — `curses` render loop: header, selectable track list with
   scroll, now-playing + progress bar + status + key hints. Non-blocking
   `getch` with a 50 ms tick.

Shutdown is exception-safe: `run_ui`'s `finally` block sends `QUIT` (then
`kill` after a 2 s grace), and `curses.wrapper` restores the terminal even on
Ctrl-C — so no zombie decoders and no garbled terminals, ever.

---

## Project structure

```
sonic/
├── sonic.py          # the entire player (executable, #!/usr/bin/env python3)
├── requirements.txt  # tinytag — optional ID3 support
└── README.md         # you are here
```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `sonic: error: 'mpg123' not found on PATH` | Install `mpg123` (see [Requirements](#requirements)) |
| `sonic: no .mp3 files in <dir>` | You're in the wrong folder, or files end in `.m4a`/`.flac` (not supported — convert or symlink `.mp3`s) |
| `terminal too small` | Resize to at least 80×24 |
| `terminal problem: …` / `not a terminal` | stdout isn't a TTY — run it interactively, not piped |
| Filenames instead of `Artist - Title`, `--:--` durations | `tinytag` not installed → `pip install -r requirements.txt` |
| No sound but UI moves | Audio output issue outside `sonic`: check volume (`alsamixer`, `pavucontrol`), and that `mpg123 file.mp3` alone makes noise |
| Leftover `mpg123` process | Shouldn't happen (graceful `QUIT` + `kill` fallback) — `pkill -f 'mpg123 --remote'` cleans up manually |

---

## Uninstall

```sh
rm ~/.local/bin/sonic            # remove the symlink
pip uninstall tinytag            # only if you want the lib gone too
```

Nothing else is ever written anywhere: no config files, no caches, no daemons.

---

## Roadmap

Ideas, roughly in order of likelihood:

- [ ] `m` mute toggle (trivial — `MUTE`/`UNMUTE` already in the protocol)
- [ ] `/` incremental search/filter in the track list
- [ ] `d` toggle: include subdirectories ("album mode")
- [ ] Persist volume in a tiny dotfile
- [ ] `--backend mpv` option for systems without `mpg123`
- [ ] Packaging: AUR / PyPI entry point

PRs welcome — it's one file, the bar is low. 🙂
