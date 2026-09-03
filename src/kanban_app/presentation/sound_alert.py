from __future__ import annotations

import math
import os
import struct
import sys
import tempfile
import wave
from pathlib import Path
from typing import Final

try:
    import winsound
except ImportError:
    winsound = None  # type: ignore[assignment]


SOUND_TYPE_LABELS: Final[dict[str, str]] = {
    "defesa_civil": "🚨 Alerta Defesa Civil (Celular)",
    "sino_suave": "🔔 Sino Suave (Moderno)",
    "sineta_discreta": "🛎️ Sineta Discreta",
    "windows": "💻 Notificação do Windows",
}

# Compatibilidade retroativa com nomes legados
_LEGACY_MAP: Final[dict[str, str]] = {
    "chime": "sino_suave",
    "bell": "sineta_discreta",
}


def _resolve_sound_file(sound_key: str) -> Path | None:
    sound_key = _LEGACY_MAP.get(sound_key, sound_key)
    filename = f"{sound_key}.wav"

    # 1. Procura na pasta assets do executável empacotado (PyInstaller)
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates = [
            exe_dir / "assets" / "sounds" / filename,
            exe_dir / "_internal" / "assets" / "sounds" / filename,
        ]
        if hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "assets" / "sounds" / filename)
        for c in candidates:
            if c.is_file():
                return c

    # 2. Procura na pasta assets do projeto em desenvolvimento
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    dev_path = project_root / "assets" / "sounds" / filename
    if dev_path.is_file():
        return dev_path

    current_dir = Path(__file__).resolve().parent.parent.parent
    dev_path2 = current_dir / "assets" / "sounds" / filename
    if dev_path2.is_file():
        return dev_path2

    # 3. Fallback: gera e grava em cache temporário no disco para garantir execução física
    temp_dir = Path(tempfile.gettempdir()) / "ProducaoOperacional" / "sounds"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / filename
    if temp_file.is_file() and temp_file.stat().st_size > 1000:
        return temp_file

    _synthesize_wav_to_file(sound_key, temp_file)
    return temp_file if temp_file.is_file() else None


def _synthesize_wav_to_file(sound_key: str, dest_path: Path) -> None:
    sample_rate = 44100
    try:
        if sound_key == "defesa_civil":
            pulses = [0.45, 0.45, 0.45]
            pause = 0.10
            total_duration = sum(pulses) + (len(pulses) - 1) * pause
            num_samples = int(sample_rate * total_duration)

            with wave.open(str(dest_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                data = bytearray()
                for i in range(num_samples):
                    t = i / sample_rate
                    is_active = False
                    cur = 0.0
                    for p in pulses:
                        if cur <= t < cur + p:
                            is_active = True
                            break
                        cur += p + pause

                    if is_active:
                        s1 = math.sin(2 * math.pi * 853.0 * t)
                        s2 = math.sin(2 * math.pi * 960.0 * t)
                        sample = (s1 + s2) * 0.45
                    else:
                        sample = 0.0

                    val = int(max(-1.0, min(1.0, sample)) * 28000)
                    data.extend(struct.pack("<h", val))
                wf.writeframes(data)

        elif sound_key == "sineta_discreta":
            duration = 0.60
            num_samples = int(sample_rate * duration)
            with wave.open(str(dest_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                data = bytearray()
                for i in range(num_samples):
                    t = i / sample_rate
                    env = math.sin(math.pi * min(1.0, t / 0.02)) * math.exp(-7.0 * t)
                    sample = env * math.sin(2 * math.pi * 1046.50 * t)
                    val = int(max(-1.0, min(1.0, sample)) * 24000)
                    data.extend(struct.pack("<h", val))
                wf.writeframes(data)

        else:  # sino_suave (padrão)
            duration = 0.80
            num_samples = int(sample_rate * duration)
            with wave.open(str(dest_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                data = bytearray()
                for i in range(num_samples):
                    t = i / sample_rate
                    if t < 0.22:
                        freq = 587.33
                        env = math.sin(math.pi * min(1.0, t / 0.03)) * math.exp(-6.0 * t)
                    else:
                        t2 = t - 0.22
                        freq = 880.00
                        env = math.sin(math.pi * min(1.0, t2 / 0.03)) * math.exp(-5.0 * t2)
                    sample = env * (0.85 * math.sin(2 * math.pi * freq * t) + 0.15 * math.sin(4 * math.pi * freq * t))
                    val = int(max(-1.0, min(1.0, sample)) * 26000)
                    data.extend(struct.pack("<h", val))
                wf.writeframes(data)
    except Exception:
        pass


def play_alert_sound(sound_type: str = "defesa_civil") -> None:
    """Toca o alerta sonoro em qualquer dispositivo de saída do Windows (HDMI, USB, P2)."""
    if winsound is None:
        return

    try:
        key = str(sound_type or "").lower().strip()
        key = _LEGACY_MAP.get(key, key)

        if key == "windows":
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return

        sound_file = _resolve_sound_file(key)
        if sound_file and sound_file.is_file():
            # Toca através do arquivo físico com SND_FILENAME: 100% garantido no Windows
            winsound.PlaySound(str(sound_file), winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            # Se o arquivo não puder ser gerado, usa o beep nativo do Windows como fallback garantido
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
