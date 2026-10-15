from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

TARGET_RATE = 16_000


class MonoDownsampler:
    """Turns interleaved int16 chunks at any rate into 16 kHz mono int16, streaming."""

    def __init__(self, in_rate: int, channels: int) -> None:
        self._channels = channels
        self._stream = soxr.ResampleStream(in_rate, TARGET_RATE, 1, dtype="float32", quality="HQ")

    def process(self, raw: bytes) -> np.ndarray:
        frames = np.frombuffer(raw, dtype=np.int16).reshape(-1, self._channels)
        mono = frames.astype(np.float32).mean(axis=1) / 32768.0
        return _to_int16(self._stream.resample_chunk(mono, last=False))

    def flush(self) -> np.ndarray:
        return _to_int16(self._stream.resample_chunk(np.zeros(0, dtype=np.float32), last=True))


def _to_int16(samples: np.ndarray) -> np.ndarray:
    return np.clip(np.round(samples * 32768.0), -32768, 32767).astype(np.int16)


def peak_dbfs(samples: np.ndarray) -> float:
    peak = int(np.max(np.abs(samples.astype(np.int32)))) if samples.size else 0
    return 20 * np.log10(max(peak, 1e-6) / 32767)


def write_mp3(wav_path: Path) -> Path:
    mp3_path = wav_path.with_suffix(".mp3")
    data, rate = sf.read(wav_path, dtype="float32")
    sf.write(mp3_path, data, rate, format="MP3")
    return mp3_path
