"""TTS WAV generator. Tries A0's speech helper, falls back to espeak-ng if available."""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from typing import Optional

log = logging.getLogger(__name__)

TTS_DIR = "/tmp/dj_booth_tts"


async def generate_tts_wav(text: str) -> Optional[str]:
    if not text.strip():
        return None
    os.makedirs(TTS_DIR, exist_ok=True)
    out = os.path.join(TTS_DIR, f"{uuid.uuid4().hex}.wav")

    # Strategy 1: A0 speech helper (if exposed)
    try:
        from helpers.speech import synthesize_to_file  # type: ignore
        ok = await synthesize_to_file(text, out)
        if ok and os.path.exists(out):
            return out
    except Exception:
        pass

    # Strategy 2: espeak-ng subprocess
    if shutil.which("espeak-ng"):
        proc = await asyncio.create_subprocess_exec(
            "espeak-ng", "-w", out, text,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        rc = await proc.wait()
        if rc == 0 and os.path.exists(out):
            return out

    log.warning("dj_booth: no TTS engine available (tried helpers.speech, espeak-ng)")
    return None
