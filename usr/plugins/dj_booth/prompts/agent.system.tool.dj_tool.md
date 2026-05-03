### dj_tool

Control the dj_booth Icecast2 stream. Use sub-methods via `dj_tool:<method>`.

**Methods**

| method | args | what it does |
|---|---|---|
| `status` | — | current stream state, now-playing, listener count |
| `search_library` | `query` (string) | search title/artist/album/genre, return up to 20 matches with paths |
| `queue_track` | `path` (string) | add a track to the playback queue |
| `skip` | — | skip the currently playing track |
| `clear_queue` | — | drop all queued tracks |
| `listener_count` | — | how many clients are tuned in |

**Examples**

Get state:
```json
{ "tool_name": "dj_tool", "method": "status" }
```

Find a track and queue it:
```json
{ "tool_name": "dj_tool", "method": "search_library", "tool_args": { "query": "blue monday" } }
```

```json
{ "tool_name": "dj_tool", "method": "queue_track", "tool_args": { "path": "/a0/usr/workdir/music/new_order.mp3" } }
```

**Notes**
- Always call `status` at the start of each DJ session to know what's playing.
- The stream emits silence when the queue is empty — keep at least one track queued.
- Listener count updates every ~5 seconds; don't poll faster.
