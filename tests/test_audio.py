from pathlib import Path

import numpy as np
import soundfile as sf

from audio import TARGET_RATE, MonoDownsampler, peak_dbfs, write_mp3


def _stereo_int16(rate: int, seconds: float, freq: float, amp: float) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    tone = (amp * 32767 * np.sin(2 * np.pi * freq * t)).astype(np.int16)
    return np.column_stack([tone, tone]).tobytes()


def _dominant_freq(samples: np.ndarray, rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(samples.astype(np.float64)))
    return float(np.fft.rfftfreq(len(samples), 1 / rate)[np.argmax(spectrum)])


def _run(rate: int, raw: bytes, chunk_frames: int) -> np.ndarray:
    ds = MonoDownsampler(in_rate=rate, channels=2)
    step = chunk_frames * 2 * 2
    parts = [ds.process(raw[i : i + step]) for i in range(0, len(raw), step)]
    parts.append(ds.flush())
    return np.concatenate(parts)


def test_48k_stereo_becomes_16k_mono_with_same_pitch_and_level() -> None:
    out = _run(48_000, _stereo_int16(48_000, 2.0, 440.0, 0.5), chunk_frames=4800)

    assert out.dtype == np.int16
    assert out.ndim == 1
    assert abs(len(out) - 2 * TARGET_RATE) < 50
    assert abs(_dominant_freq(out, TARGET_RATE) - 440.0) < 2
    assert -7.5 < peak_dbfs(out) < -5.0


def test_44k1_input_is_resampled_to_16k() -> None:
    out = _run(44_100, _stereo_int16(44_100, 1.0, 1000.0, 0.5), chunk_frames=4410)

    assert abs(len(out) - TARGET_RATE) < 50
    assert abs(_dominant_freq(out, TARGET_RATE) - 1000.0) < 2


def test_left_and_right_are_averaged() -> None:
    left = np.full(4800, 10000, dtype=np.int16)
    right = np.zeros(4800, dtype=np.int16)
    raw = np.column_stack([left, right]).tobytes()

    out = _run(48_000, raw, chunk_frames=4800)

    assert abs(int(np.median(out)) - 5000) < 100


def test_peak_dbfs_of_silence_is_very_low_and_full_scale_is_zero() -> None:
    assert peak_dbfs(np.zeros(100, dtype=np.int16)) < -90
    assert abs(peak_dbfs(np.array([32767], dtype=np.int16))) < 0.01


def test_write_mp3_makes_smaller_file_with_same_duration(tmp_path: Path) -> None:
    wav = tmp_path / "rec.wav"
    t = np.arange(TARGET_RATE * 5) / TARGET_RATE
    sf.write(wav, 0.3 * np.sin(2 * np.pi * 300 * t), TARGET_RATE, subtype="PCM_16")

    mp3 = write_mp3(wav)

    assert mp3 == tmp_path / "rec.mp3"
    assert mp3.stat().st_size < wav.stat().st_size / 4
    assert abs(sf.info(mp3).duration - 5.0) < 0.2
