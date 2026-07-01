# Transcription Watcher — Setup & Reuse Guide

Full reference for setting up the auto-transcription pipeline from scratch on any project. Written to avoid every issue encountered during the original build.

---

## What It Does

Watches a `calls/` folder. When you drop an MP3 file in, it automatically transcribes it to plain text using a local AI model running on your Mac's GPU. Output lands in `transcript/<filename>.txt`. The original MP3 moves to `calls/done/`.

No internet required after first setup. No API keys. No accounts. ~3 minutes for a 45-minute recording.

---

## Hard Requirements

| Requirement | Why |
|---|---|
| **Apple Silicon Mac** (M1/M2/M3/M4) | mlx-whisper only runs on Apple Silicon. On Intel, use `faster-whisper` instead (see [Intel fallback](#intel-fallback)) |
| **Python 3.10+** | Required by mlx-whisper and its dependencies |
| **ffmpeg** | Required by mlx-whisper for audio decoding |
| **macOS 13+** | MLX framework minimum requirement |

Check your chip:
```bash
uname -m   # must return arm64
```

---

## Folder Structure

```
your-project/
├── calls/                  # Drop MP3s here
│   └── done/               # Processed MP3s move here automatically
├── transcript/             # Transcripts (.txt) land here
│   └── errors.log          # Created only if something fails
├── transcribe_watcher.py   # Main script
├── requirements.txt        # Python dependencies
├── setup.sh                # First-run install script
├── run.sh                  # Start the watcher
└── .venv/                  # Python virtual environment (gitignored)
```

---

## Files

### `requirements.txt`

```
mlx-whisper
watchdog==4.0.0
python-dotenv==1.0.1
```

**Critical notes:**
- Do NOT pin `mlx-whisper` to a version — it updates frequently and the latest is always better
- `watchdog==4.0.0` is pinned because 5.x had breaking API changes at time of writing
- Do NOT add `torch`, `torchaudio`, `numpy`, or `pyannote.audio` — these are CPU libraries and will conflict with MLX's GPU usage

### `setup.sh`

```bash
#!/bin/bash
set -e

echo "Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

echo "Upgrading pip and installing build tools..."
pip install --upgrade pip setuptools wheel

echo "Installing dependencies (this may take a few minutes)..."
pip install -r requirements.txt

echo "Checking for ffmpeg..."
if ! command -v ffmpeg &> /dev/null; then
    echo "ERROR: ffmpeg not found. Install with: brew install ffmpeg"
    exit 1
fi

echo ""
echo "Downloading whisper-large-v3-turbo model (one-time, ~800MB)..."
.venv/bin/python3 -c "from mlx_whisper.transcribe import ModelHolder; ModelHolder.get_model('mlx-community/whisper-large-v3-turbo', dtype=None)"

echo ""
echo "Setup complete. Run './run.sh' to start the watcher."
```

**Why `pip install --upgrade pip setuptools wheel` first:**
The default venv on Python 3.10 ships with pip 21.x and setuptools 58.x. These are too old to build `openai-whisper` or several other packages. Always upgrade before installing. If you skip this and get `ModuleNotFoundError: No module named 'pkg_resources'`, this is why.

**Why `.venv/bin/python3` for the model download (not just `python3`):**
After `source .venv/bin/activate` inside a script, the `python3` command sometimes still resolves to the system Python depending on the shell environment. Using the explicit venv path is always safe.

### `run.sh`

```bash
#!/bin/bash
[ -f .env ] || { echo "ERROR: .env not found. Run ./setup.sh first."; exit 1; }
[ -f .venv/bin/activate ] || { echo "ERROR: .venv not found. Run ./setup.sh first."; exit 1; }
set -a
source .env
set +a
source .venv/bin/activate
PYTHONUNBUFFERED=1 python3 transcribe_watcher.py
```

**Why `PYTHONUNBUFFERED=1`:**
Without this, Python buffers stdout and logs don't appear in real-time — the terminal looks frozen even when transcription is actively running. This is the single most important flag for debugging.

**Why `set -a` / `set +a` around `source .env`:**
This exports all variables from `.env` as environment variables automatically, without needing `export` before each line in the `.env` file.

### `transcribe_watcher.py`

```python
import os
import shutil
import time
import logging
import traceback
import datetime
from pathlib import Path
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

load_dotenv()

try:
    import mlx_whisper
except ImportError:
    mlx_whisper = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

MODEL = "mlx-community/whisper-large-v3-turbo"


def transcribe_file(mp3_path: str, transcript_dir: str, done_dir: str) -> None:
    if mlx_whisper is None:
        raise RuntimeError("mlx-whisper not installed. Run: bash setup.sh")

    filename = os.path.basename(mp3_path)
    stem = Path(filename).stem
    os.makedirs(transcript_dir, exist_ok=True)
    os.makedirs(done_dir, exist_ok=True)

    log.info(f"📥 Transcribing: {filename}...")

    try:
        t0 = time.time()
        result = mlx_whisper.transcribe(mp3_path, path_or_hf_repo=MODEL, verbose=True)
        text = result["text"].strip()
        elapsed = time.time() - t0

        transcript_path = os.path.join(transcript_dir, f"{stem}.txt")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(text)

        log.info(f"✅ Done in {elapsed:.0f}s → transcript/{stem}.txt")
        shutil.move(mp3_path, os.path.join(done_dir, filename))
        log.info(f"📤 Moved → done/{filename}")

    except Exception as e:
        error_log = os.path.join(transcript_dir, "errors.log")
        with open(error_log, "a") as f:
            f.write(f"\n{'='*60}\n{datetime.datetime.now()} ❌ {filename}\n{traceback.format_exc()}\n")
        log.error(f"❌ Failed: {e} — details in transcript/errors.log")


class CallHandler(FileSystemEventHandler):
    def __init__(self, transcript_dir: str, done_dir: str):
        self.transcript_dir = transcript_dir
        self.done_dir = done_dir

    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith(".mp3"):
            return
        transcribe_file(event.src_path, self.transcript_dir, self.done_dir)


def main():
    calls_dir = "calls"
    transcript_dir = "transcript"
    done_dir = os.path.join(calls_dir, "done")

    os.makedirs(calls_dir, exist_ok=True)
    os.makedirs(transcript_dir, exist_ok=True)
    os.makedirs(done_dir, exist_ok=True)

    handler = CallHandler(transcript_dir=transcript_dir, done_dir=done_dir)
    observer = Observer()
    observer.schedule(handler, calls_dir, recursive=False)
    observer.start()
    log.info(f"🚀 Watching calls/ — drop an MP3 to transcribe")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
```

---

## First-Time Setup

```bash
# 1. Install ffmpeg if not already installed
brew install ffmpeg

# 2. Run setup (creates venv, installs deps, downloads model)
bash setup.sh

# 3. Start the watcher
bash run.sh
```

The model downloads once (~800MB) and is cached at `~/.cache/huggingface/hub/`. All subsequent runs use the cache — no internet needed.

---

## Daily Usage

```bash
bash run.sh
```

Then drop any MP3 into `calls/` from Finder or terminal:

```bash
cp /path/to/recording.mp3 calls/
```

You'll see live output as it transcribes:
```
2026-04-09 10:00:01 [INFO] 🚀 Watching calls/ — drop an MP3 to transcribe
2026-04-09 10:00:05 [INFO] 📥 Transcribing: recording.mp3...
[00:00.000 --> 00:04.500]  Good morning, welcome to the call.
[00:04.500 --> 00:09.200]  Thank you for joining us today.
...
2026-04-09 10:03:12 [INFO] ✅ Done in 187s → transcript/recording.txt
2026-04-09 10:03:12 [INFO] 📤 Moved → done/recording.mp3
```

Stop the watcher with `Ctrl+C`.

---

## Model Choice

The model is set at the top of `transcribe_watcher.py`:

```python
MODEL = "mlx-community/whisper-large-v3-turbo"
```

| Model | Speed | Quality | Size |
|---|---|---|---|
| `mlx-community/whisper-large-v3-turbo` | ~3 min / 45 min audio | Best | ~800MB |
| `mlx-community/whisper-medium-mlx` | ~5 min / 45 min audio | Good | ~500MB |
| `mlx-community/whisper-small-mlx` | ~2 min / 45 min audio | Decent | ~250MB |

To change model, edit the `MODEL` line and re-run. The new model downloads automatically on first use.

---

## Logging

**Live output during transcription** comes from `verbose=True` in the `mlx_whisper.transcribe()` call. Each line shows a time range and the decoded text. This is your progress indicator — if you see lines appearing every few seconds, it's working.

**Application logs** use Python's `logging` module at INFO level:
```
2026-04-09 10:00:05 [INFO] 📥 Transcribing: recording.mp3...
2026-04-09 10:03:12 [INFO] ✅ Done in 187s → transcript/recording.txt
```

**Error logs** are written to `transcript/errors.log` with full Python tracebacks. Check this file if a transcription fails silently.

**If logs don't appear in real time:** Make sure `PYTHONUNBUFFERED=1` is set in `run.sh`. Without it, Python buffers output and nothing appears until the process ends.

---

## Error Reference

### `ModuleNotFoundError: No module named 'pkg_resources'`
**Cause:** pip/setuptools too old in the venv (Python 3.10 default is pip 21.x).
**Fix:** `setup.sh` now runs `pip install --upgrade pip setuptools wheel` first. If you hit this, wipe the venv and re-run setup:
```bash
rm -rf .venv && bash setup.sh
```

### `OSError: Symbol not found: _aoti_torch_abi_version`
**Cause:** `torchaudio` version doesn't match `torch` version. This happens when you mix torch==2.2.0 with a newer torchaudio.
**Fix:** Don't use torch/torchaudio at all with the mlx-whisper stack. Remove them from requirements.txt.

### `RuntimeError: Numpy is not available`
**Cause:** NumPy 2.x is incompatible with torch 2.2.x.
**Fix:** Again, don't mix torch with the mlx stack. If you need torch for something else, pin `numpy<2`.

### `Pipeline.from_pretrained() got an unexpected keyword argument 'token'`
**Cause:** pyannote.audio 3.1.x uses `use_auth_token=`, not `token=`. The HuggingFace hub changed the parameter name in a newer version but pyannote hadn't updated.
**Fix:** Irrelevant with the mlx-whisper stack (no pyannote). If you re-add pyannote, use `use_auth_token=` not `token=`.

### Watcher starts but nothing happens when MP3 is dropped
**Cause:** watchdog on macOS sometimes misses events on network drives or certain folder types.
**Fix:** Make sure you're working on a local drive (not iCloud Drive, not NFS). The `calls/` folder must be local.

### Terminal looks frozen, no output
**Cause:** Missing `PYTHONUNBUFFERED=1` in run.sh, or `verbose=True` not set on the transcribe call.
**Fix:** Both are already set in the current version. If you copy the script to a new project, don't forget either.

---

## Intel Fallback

If you're on an Intel Mac or Linux, replace the mlx stack with `faster-whisper`:

**`requirements.txt`:**
```
faster-whisper==1.1.1
torch==2.2.0
torchaudio==2.2.0
numpy<2
watchdog==4.0.0
python-dotenv==1.0.1
```

**In `transcribe_watcher.py`**, replace the import and transcription:
```python
# Replace:
try:
    import mlx_whisper
except ImportError:
    mlx_whisper = None

MODEL = "mlx-community/whisper-large-v3-turbo"

# With:
try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None
```

And replace the transcription call:
```python
# Replace:
result = mlx_whisper.transcribe(mp3_path, path_or_hf_repo=MODEL, verbose=True)
text = result["text"].strip()

# With:
model = WhisperModel("medium", device="cpu", compute_type="int8")
raw_segments, _ = model.transcribe(mp3_path, beam_size=5)
text = " ".join(seg.text.strip() for seg in raw_segments)
```

Speed on Intel CPU: ~15-30 min for a 45-min call (vs ~3 min on Apple Silicon).

---

## Reusing in a New Project

Minimum files to copy:
```
transcribe_watcher.py
requirements.txt
setup.sh
run.sh
```

Then:
```bash
mkdir calls transcript
chmod +x setup.sh run.sh
bash setup.sh
bash run.sh
```

The model is cached globally at `~/.cache/huggingface/hub/` — it won't re-download across projects.

---

## What Was Deliberately Left Out

- **Speaker labels** — pyannote.audio diarization was evaluated and dropped. It added 20-40 min of CPU processing per file and required a HuggingFace account. For LLM prompting workflows, the text alone is sufficient.
- **Timestamps in output** — the transcript is plain text, no `[00:05]` markers. mlx_whisper does produce segment timestamps internally (`verbose=True` shows them) but they're not written to the output file.
- **File format support beyond MP3** — mlx_whisper via ffmpeg can handle most audio formats (m4a, wav, mp4, etc.). To support them, change the `.endswith(".mp3")` check in `CallHandler.on_created` to a broader check.
