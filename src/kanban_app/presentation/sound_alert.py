from __future__ import annotations

import io
import math
import struct
import wave
from typing import Final

try:
    import winsound
except ImportError:
    winsound = None  # type: ignore[assignment]


SOUND_TYPE_LABELS: Final[dict[str, str]] = {
    "chime": "Sino Suave (Recomendado)",
    "bell": "Sineta Discreta",
    "windows": "Notificação do Windows",
}

_SOUND_CACHE: dict[str, bytes] = {}


def _generate_wav(sound_type: str) -> bytes:
    """Gera um áudio WAV suave de alerta em memória com decaimento exponencial."""
    sample_rate = 44100
    duration = 0.70
    num_samples = int(sample_rate * duration)
    buf = io.BytesIO()

    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        data = bytearray()

        if sound_type == "bell":
            freq1, freq2 = 698.46, 1046.50  # F5 -> C6
        else:
            freq1, freq2 = 587.33, 880.00   # D5 -> A5 (chime moderno)

        split_time = 0.18
        for i in range(num_samples):
            t = i / sample_rate
            if t < split_time:
                freq = freq1
                envelope = math.sin(math.pi * min(1.0, t / 0.03)) * math.exp(-6.5 * t)
            else:
                t2 = t - split_time
                freq = freq2
                envelope = math.sin(math.pi * min(1.0, t2 / 0.03)) * math.exp(-5.0 * t2)

            # Tom senoidal puro com harmônico suave para timbre metálico sutil
            sample = envelope * (0.88 * math.sin(2 * math.pi * freq * t) + 0.12 * math.sin(4 * math.pi * freq * t))
            val = int(max(-1.0, min(1.0, sample)) * 26000)
            data.extend(struct.pack("<h", val))

        wf.writeframes(data)

    return buf.getvalue()


def play_alert_sound(sound_type: str = "chime") -> None:
    """Toca o alerta sonoro de forma assíncrona sem travar a interface da TV."""
    if winsound is None:
        return

    try:
        sound_key = sound_type.lower()
        if sound_key == "windows":
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return

        if sound_key not in _SOUND_CACHE:
            _SOUND_CACHE[sound_key] = _generate_wav(sound_key)

        wav_bytes = _SOUND_CACHE[sound_key]
        winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC)
    except Exception:
        # Falhas em placas de som ausentes ou desligadas não devem quebrar o sistema
        pass
