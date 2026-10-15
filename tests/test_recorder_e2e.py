"""End-to-end: plays a quiet tone through the real speakers and checks the recorder captured it."""

import subprocess
import sys
import threading
from pathlib import Path

import numpy as np
import pyaudiowpatch as pyaudio
import pytest
import soundfile as sf

from audio import TARGET_RATE

ROOT = Path(__file__).resolve().parent.parent


def _has_loopback() -> bool:
    try:
        with pyaudio.PyAudio() as pa:
            pa.get_default_wasapi_loopback()
        return True
    except (OSError, LookupError):
        return False


pytestmark = pytest.mark.skipif(not _has_loopback(), reason="no WASAPI loopback device")


def _play_tone(seconds: float, freq: float = 440.0) -> None:
    with pyaudio.PyAudio() as pa:
        rate = 48_000
        t = np.arange(int(rate * seconds)) / rate
        tone = (0.02 * 32767 * np.sin(2 * np.pi * freq * t)).astype(np.int16)
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=rate, output=True)
        stream.write(tone.tobytes())
        stream.stop_stream()
        stream.close()


def _cli(*args: str, out_dir: Path) -> str:
    result = subprocess.run(
        [sys.executable, str(ROOT / "recorder.py"), *args, "--dir", str(out_dir)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_sound_check_hears_a_tone(tmp_path: Path) -> None:
    player = threading.Timer(1.0, _play_tone, args=(3.0,))
    player.start()
    out = _cli("test", "--seconds", "5", out_dir=tmp_path)
    player.join()

    assert "HEARD SOUND" in out


def test_start_then_stop_produces_16k_mono_wav_and_mp3(tmp_path: Path) -> None:
    _cli("start", out_dir=tmp_path)
    _cli("status", out_dir=tmp_path)
    _play_tone(3.0, freq=600.0)
    out = _cli("stop", out_dir=tmp_path)

    wavs = list(tmp_path.glob("*.wav"))
    mp3s = list(tmp_path.glob("*.mp3"))
    assert len(wavs) == 1 and len(mp3s) == 1
    assert str(wavs[0]) in out

    info = sf.info(wavs[0])
    assert info.samplerate == TARGET_RATE
    assert info.channels == 1
    assert info.subtype == "PCM_16"
    assert info.duration >= 3.0

    data, _ = sf.read(wavs[0], dtype="int16")
    spectrum = np.abs(np.fft.rfft(data.astype(np.float64)))
    peak_freq = np.fft.rfftfreq(len(data), 1 / TARGET_RATE)[np.argmax(spectrum)]
    assert abs(peak_freq - 600.0) < 5
