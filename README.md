# speaker-recorder

Records **everything this Windows PC plays through its speakers** (calls, videos, meetings) to a
**16 kHz mono WAV** — the format the transcription takes — plus a small **MP3 copy** for sending.
Only the speaker output is recorded, never the microphone. No extra drivers needed (uses WASAPI
loopback via `pyaudiowpatch`).

## For the Claude setting this up

Run these steps for the user in PowerShell, in order. Windows 10/11 and Python 3.10+ required
(`python --version`; if missing: `winget install Python.Python.3.12`, then open a new terminal).

### 1. Install

```powershell
git clone https://github.com/niclom12/speaker-recorder.git
cd speaker-recorder
python -m venv venv
.\venv\Scripts\python -m pip install -r requirements.txt
```

### 2. 10-second sound check (proves it hears the speakers)

Ask the user to play something (a YouTube video is fine) and keep it playing, then run:

```powershell
.\venv\Scripts\python recorder.py test
```

- `HEARD SOUND (peak … dBFS)` → working. Go to step 3.
- `SILENT` → fix, then re-run the test:
  - **Windows sound is muted** → unmute it. Mute makes the recording silent. A low volume is fine
    (volume does not affect the recording level), so the user can turn it right down instead.
  - Audio is going to a different device (e.g. Bluetooth headset) than the Windows default output.
    Make the device in use the default in Settings → System → Sound → Output, then re-test.

### 3. Start (runs in the background — the terminal can be closed)

```powershell
.\venv\Scripts\python recorder.py start
```

Check it any time with `.\venv\Scripts\python recorder.py status`.

### 4. Stop

```powershell
.\venv\Scripts\python recorder.py stop
```

This prints the two files, in the `recordings\` folder:

```
WAV (16 kHz mono): ...\recordings\speakers-20261015-143000.wav   (~115 MB per hour)
MP3 (to send):     ...\recordings\speakers-20261015-143000.mp3   (about a tenth of that)
```

### 5. Send the file

Send the **MP3** (small enough for email/WhatsApp for recordings up to roughly an hour). If the
recipient specifically asks for the WAV, send that instead — use a file-sharing link (Google Drive,
OneDrive, WeTransfer) for anything over ~25 MB. Open the folder with `explorer recordings`.

## Notes

- Silence is kept: a 1-hour session gives a 1-hour file even if nothing played for parts of it.
- Always stop with `recorder.py stop`. If the PC shuts down or the process is killed mid-recording,
  the WAV header is not finalised and the file may need repair (e.g. open and re-export in Audacity).
- If something fails in the background, details are in `recordings\recorder.log`.
- If the output device changes mid-recording (e.g. headphones plugged in), stop and start again.

## Development

```powershell
.\venv\Scripts\python -m pip install pytest
.\venv\Scripts\python -m pytest -o pythonpath=.
```

The end-to-end tests play a quiet tone through the speakers and need them unmuted.
