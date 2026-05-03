# dj_booth — Slice 1 (Stream Backbone)

Local Icecast2 streaming server packaged as an Agent Zero plugin. Any ICY-compatible client (Winamp, VLC, foobar2000, browser `<audio>`) can tune in.

## Status

Slice 1 of 5. Ships: Icecast2 + streaming engine (liquidsoap preferred, ffmpeg fallback) + library scan + minimal start/stop UI.

Coming in later slices: agent DJ tool (Slice 2), full DJ booth UI with two decks + EFX (Slice 3), BPM/key/spectrum analysis (Slice 4), mic + cue/loop/scratch (Slice 5).

## Prerequisites

- Agent Zero in Docker with `apt-get` available
- Port 8000 mapped on the container: `docker run -p 8000:8000 ...`
- Music files copied into the configured `music_dir` (default `/a0/usr/workdir/music`)

## Install

1. Open the Plugins UI in Agent Zero
2. Install `dj_booth`. The install hook runs `apt-get install icecast2 liquidsoap ffmpeg` and `pip install mutagen`.
3. Open Settings → DJ Booth and adjust passwords + paths
4. Click **Execute** in the plugin row to start the stack

If liquidsoap is unavailable on the host, the engine falls back to ffmpeg automatically (badge will read `FFMPEG (fallback)`). Streaming still works; brief silence between tracks is expected.

## Use

- Open the **🎧 DJ Booth** sidebar button → minimal control panel modal
- Click **Scan** in the Library panel after copying files into `music_dir`
- Double-click a track to queue it
- **Skip** / **Clear** buttons control the queue
- Listeners connect to `http://<host>:8000/stream` from VLC, Winamp, or browser

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
