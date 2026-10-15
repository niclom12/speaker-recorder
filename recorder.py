"""Record whatever this Windows PC plays through its speakers to a 16 kHz mono WAV (+ MP3 copy).

Usage:
    python recorder.py test [--seconds 10]   sound check, records in the foreground
    python recorder.py start                 start recording in the background
    python recorder.py status                is a recording running?
    python recorder.py stop                  stop and print the file paths
"""

import argparse
import ctypes
import json
import subprocess
import sys
import time
import traceback
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pyaudiowpatch as pyaudio

from audio import TARGET_RATE, MonoDownsampler, peak_dbfs, write_mp3

DEFAULT_DIR = Path(__file__).resolve().parent / "recordings"
SILENCE_DBFS = -50.0


@dataclass
class Session:
    pid: int
    wav: str
    started: str


class Paths:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.lock = base / ".recording.json"
        self.stop_flag = base / ".stop"
        self.log = base / "recorder.log"


def _is_running(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return code.value == 259  # STILL_ACTIVE


def _active_session(paths: Paths) -> Session | None:
    if not paths.lock.exists():
        return None
    session = Session(**json.loads(paths.lock.read_text()))
    if _is_running(session.pid):
        return session
    paths.lock.unlink(missing_ok=True)
    return None


def record(wav_path: Path, should_stop) -> float:
    """Capture speaker output into wav_path until should_stop() is true. Returns peak dBFS."""
    with pyaudio.PyAudio() as pa:
        loopback = pa.get_default_wasapi_loopback()
        rate = int(loopback["defaultSampleRate"])
        channels = loopback["maxInputChannels"]
        speakers = pa.get_host_api_info_by_type(pyaudio.paWASAPI)["defaultOutputDevice"]

        # Windows sends nothing on loopback while nothing plays, which would cut silent gaps
        # out of the recording. Playing digital silence keeps the timeline continuous.
        def silence(_in, frame_count, _info, _status):
            return bytes(frame_count * channels * 2), pyaudio.paContinue

        keepalive = pa.open(
            format=pyaudio.paInt16, channels=channels, rate=rate, output=True,
            output_device_index=speakers, stream_callback=silence,
        )
        capture = pa.open(
            format=pyaudio.paInt16, channels=channels, rate=rate, input=True,
            input_device_index=loopback["index"], frames_per_buffer=rate // 10,
        )
        downsampler = MonoDownsampler(rate, channels)
        peak = -120.0
        with wave.open(str(wav_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(TARGET_RATE)
            while not should_stop():
                chunk = downsampler.process(capture.read(rate // 10, exception_on_overflow=False))
                peak = max(peak, peak_dbfs(chunk))
                wav.writeframes(chunk.tobytes())
            wav.writeframes(downsampler.flush().tobytes())
        capture.close()
        keepalive.close()
    return peak


def cmd_run(paths: Paths) -> None:
    """The background worker that `start` launches."""
    wav_path = paths.base / f"speakers-{datetime.now():%Y%m%d-%H%M%S}.wav"
    session = Session(pid=_own_pid(), wav=str(wav_path), started=datetime.now().isoformat(timespec="seconds"))
    paths.lock.write_text(json.dumps(asdict(session)))
    try:
        record(wav_path, paths.stop_flag.exists)
        write_mp3(wav_path)
    except Exception:
        with paths.log.open("a") as log:
            log.write(f"{datetime.now().isoformat()} {traceback.format_exc()}\n")
        raise
    finally:
        paths.stop_flag.unlink(missing_ok=True)
        paths.lock.unlink(missing_ok=True)


def _own_pid() -> int:
    return ctypes.windll.kernel32.GetCurrentProcessId()


def cmd_start(paths: Paths) -> int:
    session = _active_session(paths)
    if session:
        print(f"Already recording to {session.wav} (since {session.started}).")
        return 1
    paths.stop_flag.unlink(missing_ok=True)
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen(
        [str(pythonw), str(Path(__file__).resolve()), "run", "--dir", str(paths.base)],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
    for _ in range(100):
        time.sleep(0.1)
        session = _active_session(paths)
        if session:
            print(f"Recording speakers to {session.wav}")
            print("Stop with: python recorder.py stop")
            return 0
    print(f"Recorder did not start. See {paths.log}")
    return 1


def cmd_stop(paths: Paths) -> int:
    session = _active_session(paths)
    if not session:
        print("No recording is running.")
        return 1
    paths.stop_flag.touch()
    for _ in range(600):
        if not _is_running(session.pid):
            break
        time.sleep(0.1)
    wav = Path(session.wav)
    mp3 = wav.with_suffix(".mp3")
    if not mp3.exists():
        print(f"Recording stopped but files are incomplete. See {paths.log}")
        return 1
    with wave.open(str(wav)) as w:
        minutes = w.getnframes() / w.getframerate() / 60
    print(f"Stopped after {minutes:.1f} min.")
    print(f"WAV (16 kHz mono): {wav}  ({wav.stat().st_size / 1e6:.1f} MB)")
    print(f"MP3 (to send):     {mp3}  ({mp3.stat().st_size / 1e6:.1f} MB)")
    return 0


def cmd_status(paths: Paths) -> int:
    session = _active_session(paths)
    print(f"Recording to {session.wav} since {session.started}." if session else "Not recording.")
    return 0


def cmd_test(paths: Paths, seconds: float) -> int:
    wav = paths.base / "sound-check.wav"
    deadline = time.monotonic() + seconds
    print(f"Listening to the speakers for {seconds:g} s - play something now...")
    peak = record(wav, lambda: time.monotonic() >= deadline)
    if peak > SILENCE_DBFS:
        print(f"HEARD SOUND (peak {peak:.1f} dBFS). Saved {wav}")
    else:
        print(
            f"SILENT (peak {peak:.1f} dBFS). Either nothing was playing, Windows sound is MUTED "
            "(muted = silent recording; low volume is fine), or audio goes to a different "
            "device than the default speakers."
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Record speaker output to WAV.")
    parser.add_argument("command", choices=["start", "stop", "status", "test", "run"])
    parser.add_argument("--seconds", type=float, default=10.0, help="length of the sound check")
    parser.add_argument("--dir", type=Path, default=DEFAULT_DIR, help="where recordings go")
    args = parser.parse_args()

    args.dir.mkdir(parents=True, exist_ok=True)
    paths = Paths(args.dir)
    if args.command == "run":
        cmd_run(paths)
        return 0
    if args.command == "start":
        return cmd_start(paths)
    if args.command == "stop":
        return cmd_stop(paths)
    if args.command == "status":
        return cmd_status(paths)
    return cmd_test(paths, args.seconds)


if __name__ == "__main__":
    sys.exit(main())
