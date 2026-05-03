# 🎧 DJ Booth

Turn Agent Zero into a personal radio station you can share with anyone.

## What you get

- A live audio stream anyone can tune into from a web browser, VLC, Winamp, or any modern music player
- A simple control panel inside Agent Zero — pick songs, adjust volume, do crossfades, add effects
- Optional: let **DJ Zero** (an AI agent) pick tracks for you

## Quick start (3 clicks)

1. **Install:** Open the **Plugins** menu, find **DJ Booth**, click **Install**. Agent Zero installs everything for you — no terminal commands needed. Watch the install log; you'll see "All set!" when it's done.
2. **Add music:** Copy your music files into the Music Folder shown in **Settings → DJ Booth** (default `/a0/usr/workdir/music`). Most common formats work: MP3, FLAC, WAV, OGG, M4A.
3. **Start:** Click the **🎧 DJ Booth** button in the sidebar, then **Start**. Click **Scan** in the Library panel, then double-click any song to play it.

That's it. The stream is live.

## How listeners tune in

Once the stream is running, the DJ Booth shows a **Listener Help** panel with:

- A big green **▶ Tune in** button — click it to open the stream in your own browser
- A **Copy URL** button — paste that URL anywhere you want to share

Send the URL to anyone. They can:

- Open it in any modern web browser → audio just plays
- Open VLC → **File → Open Network Stream** → paste the URL
- Open Winamp → **Add URL** → paste

## Letting AI run the station

Spawn the **DJ Zero** subordinate agent. It will pick tracks for you. Currently it auto-selects songs from your library; future updates add commentary and crossfading.

## Performance features

Once the stream is running, the booth gives you:

- **Two decks** (A and B) with independent queues — pick a deck, then double-click a track in the Library to load it
- **Crossfader** to mix between decks; per-deck volume and 3-band EQ
- **Pitch slider** (±6 semitones)
- **Effects rack** — reverb, delay, low-pass filter
- **Live spectrum visualizer**
- **BPM and key detection** — click ⚡ on any library row
- **Voice announcements** — type something into the Announce box and click Speak

## Need help sharing the stream beyond this computer?

The stream lives at `http://<your-computer>:8000/stream`.

- **Same wifi?** Replace `localhost` with your computer's local IP address (you can ask Agent Zero "what's my local IP?").
- **Anywhere on the internet?** Your Agent Zero installer needs to forward port 8000 — ask whoever set up Agent Zero for you. The booth shows a friendly hint if no one has connected after two minutes.

## Troubleshooting

| Symptom | What it means | What to do |
|---|---|---|
| Toast: "That port is already taken" | Something else on your computer uses port 8000 | Open **Settings → DJ Booth**, change the Stream Port (try 8800), and Start again |
| Engine badge says **FFMPEG (fallback)** | Liquidsoap couldn't be installed automatically | Streaming still works. Brief silence between tracks is normal in fallback mode. |
| No audio in VLC | The queue is empty — there's nothing playing | In the booth's Library, double-click a track |
| Library shows 0 tracks after Scan | Music folder is empty or path is wrong | Check the path in **Settings → DJ Booth** and copy your files in |
| Booth restart left things behind | A process didn't shut down cleanly last time | DJ Booth cleans up automatically the next time you Start; no action needed |

## For developers

### Architecture

See [`docs/superpowers/specs/2026-05-03-dj-booth-slice-1-design.md`](../../../docs/superpowers/specs/2026-05-03-dj-booth-slice-1-design.md) for the full design across slices 1-5.

### Slices delivered

- **Slice 1**: lifecycle, config, single-deck streaming
- **Slice 2**: DJ Zero agent + library scan
- **Slice 3**: two-deck booth, mixer, EQ, liquidsoap engine
- **Slice 4**: BPM/key analysis, waveforms, real-time spectrum
- **Slice 5**: pitch, EFX (reverb/delay/filter), TTS announcements, mic capture stub

Mic input is stubbed (full implementation deferred). Cue/loop/scratch deferred.

### What the install hook does

Runs `apt-get install icecast2 liquidsoap ffmpeg libaubio-dev libsndfile1 portaudio19-dev` and `pip install mutagen aubio numpy scipy` plus best-effort `pyaudio`. Falls back gracefully if any individual package is unavailable.

### Engine fallback

When liquidsoap is unavailable, the engine falls back to ffmpeg automatically. Streaming still works; deck routing, crossfader, volume, and EQ controls become no-ops in fallback mode (warnings in the server log).

### License

MIT.
