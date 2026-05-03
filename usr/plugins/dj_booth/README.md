# dj_booth — Slice 4 (Analysis & Visualization)

Local Icecast2 streaming server packaged as an Agent Zero plugin. Any ICY-compatible client (Winamp, VLC, foobar2000, browser `<audio>`) can tune in.

## Status

Slice 4 of 5. Ships: Icecast2 + 2-deck liquidsoap engine (ffmpeg single-stream fallback) + library scan + agent `dj_tool` + two-deck DJ booth UI with crossfader, per-deck volume, 3-band EQ per deck, deck-targeted queue/skip/clear, **on-demand BPM + key detection (aubio + Krumhansl-Schmuckler chromagram)**, **pre-computed waveform peaks rendered to canvas per deck**, and a **real-time 64-band spectrum analyzer** at the top of the mixer panel.

Coming in Slice 5: mic input + cue/loop/scratch + EFX + BPM-sync.

## Prerequisites

- Agent Zero in Docker with `apt-get` available
- Port 8000 mapped on the container: `docker run -p 8000:8000 ...`
- Music files copied into the configured `music_dir` (default `/a0/usr/workdir/music`)

## Install

1. Open the Plugins UI in Agent Zero
2. Install `dj_booth`. The install hook runs `apt-get install icecast2 liquidsoap ffmpeg libaubio-dev libsndfile1` and `pip install mutagen aubio numpy scipy`.
3. Open Settings → DJ Booth and adjust passwords + paths
4. Click **Execute** in the plugin row to start the stack

If liquidsoap is unavailable on the host, the engine falls back to ffmpeg automatically (badge will read `FFMPEG (fallback)`). Streaming still works; brief silence between tracks is expected.

## Use

- Open the **🎧 DJ Booth** sidebar button → two-deck booth modal
- Click **Scan** in the Library panel after copying files into `music_dir`
- Click a deck panel (A or B) to select it as the active target
- Double-click a library track to queue on the selected deck, or use the **→A** / **→B** buttons
- Drag the **Crossfader** to mix between decks; per-deck **Volume** + 3-band **EQ** (low/mid/high) sliders shape each channel
- **Skip** / **Clear** buttons act on the deck they belong to
- Click the **⚡** button on a library row to detect BPM, key, and pre-compute the waveform — values appear inline once the analysis completes
- The mixer panel's spectrum bars animate in real time while the stream is live
- Listeners connect to `http://<host>:8000/stream` from VLC, Winamp, or browser

> **ffmpeg fallback note:** when liquidsoap is unavailable, the engine plays a single sequential queue; deck routing, crossfader, volume and EQ controls become no-ops (warnings in the server log).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Port 8000 in use" toast | Another icecast or unrelated service on 8000 | Change `icecast_port` in settings, restart |
| `FFMPEG (fallback)` badge | liquidsoap binary not in `$PATH` | `apt-get install liquidsoap`; restart |
| No audio in VLC | Stream is silent because queue is empty | Queue a track from the Library panel |
| Library shows 0 tracks after scan | `music_dir` empty or wrong path | Verify path in Settings, copy files in, click Scan again |
| Plugin restart leaves orphan processes | Manual SIGKILL'd process | Stale-PID sweep at next start cleans up; verify with `pgrep icecast2 liquidsoap ffmpeg` |

## Architecture

See `docs/superpowers/specs/2026-05-03-dj-booth-slice-1-design.md`.

## License

MIT.
