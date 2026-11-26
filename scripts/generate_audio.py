#!/usr/bin/env python3
"""Generates listening-comprehension audio with OmniVoice Q8.

Reads each MCQQuestion's dialogueScript and synthesizes it with
omnivoice.cpp (https://github.com/ServeurpersoCom/omnivoice.cpp), one
designed voice per speaker, concatenated with a short silence between
turns. The Q8 weights are CC-BY-NC and are never committed. Output WAVs
are gitignored under public/audio/.

The weights live in LM Studio's model folder after:

    lms import omnivoice-base-Q8_0.gguf --user-repo Serveurperso/OmniVoice-GGUF --copy -y
    lms import omnivoice-tokenizer-Q8_0.gguf --user-repo Serveurperso/OmniVoice-GGUF --copy -y

LM Studio stores those files. It does not synthesize speech. This script
calls the omnivoice-tts binary (OMNIVOICE_BIN, or ~/.local/share/omnivoice).

Usage:
    python3 scripts/generate_audio.py [--exam tef|tcf|all] [--force]
"""

import argparse
import os
import subprocess
import tempfile
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTENT_ROOT = REPO_ROOT / "content"
PUBLIC_ROOT = REPO_ROOT / "public"

SILENCE_SECONDS = 0.45
BASE_NAME = "omnivoice-base-Q8_0.gguf"
CODEC_NAME = "omnivoice-tokenizer-Q8_0.gguf"
# Spoken once per voice, then cloned for every line of that speaker so the
# timbre stays put. The duration is long enough that the reference itself
# is not clipped; later lines inherit its pace.
REFERENCE_TEXT = "Bonjour. Je parle français, calmement et clairement, jusqu'à la fin de la phrase."
REFERENCE_DURATION_SECONDS = 8.0

# One instruct string per dialogue voice id. Categories are mutually
# exclusive inside OmniVoice: gender, age, pitch.
VOICE_INSTRUCT = {
    "estelle": "female, young adult, moderate pitch",
    "cosette": "female, young adult, high pitch",
    "jean": "male, middle-aged, moderate pitch",
    "charles": "male, young adult, low pitch",
    "marius": "male, young adult, high pitch",
    "javert": "male, middle-aged, low pitch",
    "george": "male, elderly, low pitch",
}
VOICE_SEED = {
    "estelle": 22,
    "cosette": 27,
    "jean": 11,
    "charles": 33,
    "marius": 44,
    "javert": 55,
    "george": 66,
}


def load_questions(exam: str) -> list[dict]:
    path = CONTENT_ROOT / exam / "comprehension_orale" / "questions.json"
    if not path.exists():
        return []
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path is not None and path.is_file():
            return path
    return None


def find_named(filename: str) -> Path | None:
    roots = [
        Path.home() / ".lmstudio" / "models",
        Path.home() / ".local" / "share" / "omnivoice" / "models",
    ]
    for root in roots:
        if not root.is_dir():
            continue
        match = next(root.rglob(filename), None)
        if match is not None:
            return match
    return None


def resolve_runtime() -> tuple[Path, Path, Path]:
    binary = first_existing(
        [
            Path(os.environ["OMNIVOICE_BIN"]) if os.environ.get("OMNIVOICE_BIN") else None,
            Path.home() / ".local" / "share" / "omnivoice" / "omnivoice-tts",
        ]
    )
    model = first_existing(
        [Path(os.environ["OMNIVOICE_MODEL"]) if os.environ.get("OMNIVOICE_MODEL") else None]
    ) or find_named(BASE_NAME)
    codec = first_existing(
        [Path(os.environ["OMNIVOICE_CODEC"]) if os.environ.get("OMNIVOICE_CODEC") else None]
    ) or find_named(CODEC_NAME)
    missing = []
    if binary is None:
        missing.append("omnivoice-tts (set OMNIVOICE_BIN, or install it at ~/.local/share/omnivoice/omnivoice-tts)")
    if model is None:
        missing.append(f"{BASE_NAME} (import it into LM Studio, or set OMNIVOICE_MODEL)")
    if codec is None:
        missing.append(f"{CODEC_NAME} (import it into LM Studio, or set OMNIVOICE_CODEC)")
    if missing:
        raise SystemExit(
            "OmniVoice Q8 is not installed:\n- "
            + "\n- ".join(missing)
            + "\nWeights: https://huggingface.co/Serveurperso/OmniVoice-GGUF (CC-BY-NC)."
            + "\nRuntime: https://github.com/ServeurpersoCom/omnivoice.cpp"
        )
    return binary, model, codec


def synthesize(
    binary: Path,
    model: Path,
    codec: Path,
    text: str,
    voice: str,
    out_path: Path,
    *,
    reference: tuple[Path, Path] | None = None,
    duration_seconds: float | None = None,
) -> None:
    instruct = VOICE_INSTRUCT.get(voice)
    if instruct is None:
        raise SystemExit(f"No OmniVoice instruct for voice {voice!r}. Add it to VOICE_INSTRUCT.")
    command = [
        str(binary),
        "--model",
        str(model),
        "--codec",
        str(codec),
        "--lang",
        "french",
        "--instruct",
        instruct,
        "--seed",
        str(VOICE_SEED[voice]),
        "-o",
        str(out_path),
    ]
    if duration_seconds is not None:
        command.extend(["--duration", str(duration_seconds)])
    if reference is not None:
        ref_wav, ref_text = reference
        command.extend(["--ref-wav", str(ref_wav), "--ref-text", str(ref_text)])
    device = os.environ.get("OMNIVOICE_DEVICE")
    if device:
        command[1:1] = ["--device", device]
    completed = subprocess.run(command, input=text.encode("utf-8"), capture_output=True)
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise SystemExit(f"omnivoice-tts failed for voice {voice}:\n{detail}")


def voice_cache_dir() -> Path:
    path = Path.home() / ".local" / "share" / "omnivoice" / "voices"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reference_for(binary: Path, model: Path, codec: Path, voice: str) -> tuple[Path, Path]:
    """One finished take per voice. Dialogue lines clone it so the speaker stays the same person."""
    cache = voice_cache_dir()
    ref_wav = cache / f"{voice}.wav"
    ref_text = cache / f"{voice}.txt"
    signature = f"{VOICE_INSTRUCT[voice]}|{VOICE_SEED[voice]}|{REFERENCE_TEXT}|{REFERENCE_DURATION_SECONDS}"
    stamp = cache / f"{voice}.stamp"
    if ref_wav.is_file() and ref_text.is_file() and stamp.is_file() and stamp.read_text(encoding="utf-8") == signature:
        return ref_wav, ref_text
    print(f"recording reference voice: {voice}")
    synthesize(
        binary,
        model,
        codec,
        REFERENCE_TEXT,
        voice,
        ref_wav,
        duration_seconds=REFERENCE_DURATION_SECONDS,
    )
    ref_text.write_text(REFERENCE_TEXT, encoding="utf-8")
    stamp.write_text(signature, encoding="utf-8")
    return ref_wav, ref_text


def read_wav(path: Path) -> tuple[object, bytes]:
    with wave.open(str(path), "rb") as handle:
        return handle.getparams(), handle.readframes(handle.getnframes())


def write_dialogue(turn_paths: list[Path], out_path: Path) -> None:
    params, _ = read_wav(turn_paths[0])
    silence = b"\x00" * (
        int(params.framerate * SILENCE_SECONDS) * params.sampwidth * params.nchannels
    )
    pieces: list[bytes] = []
    for index, path in enumerate(turn_paths):
        turn_params, frames = read_wav(path)
        if (
            turn_params.framerate != params.framerate
            or turn_params.sampwidth != params.sampwidth
            or turn_params.nchannels != params.nchannels
        ):
            raise SystemExit(f"Unexpected WAV format from OmniVoice: {path}")
        if index:
            pieces.append(silence)
        pieces.append(frames)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as handle:
        handle.setparams(params)
        handle.writeframes(b"".join(pieces))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam", choices=["tef", "tcf", "all"], default="all")
    parser.add_argument("--force", action="store_true", help="Regenerate even if the audio file already exists")
    args = parser.parse_args()

    exams = ["tef", "tcf"] if args.exam == "all" else [args.exam]
    pending = []
    for exam in exams:
        for question in load_questions(exam):
            if question.get("stimulusType") != "audio" or not question.get("dialogueScript"):
                continue
            out_path = PUBLIC_ROOT / question["stimulusContent"].lstrip("/")
            if out_path.exists() and not args.force:
                print(f"skip (exists): {question['id']}")
                continue
            pending.append((question, out_path))

    if not pending:
        print("Nothing to generate.")
        return

    binary, model, codec = resolve_runtime()
    print(f"OmniVoice Q8 via {binary}")
    print(f"model: {model}")
    print(f"codec: {codec}")

    with tempfile.TemporaryDirectory(prefix="omnivoice-") as tmp:
        tmp_dir = Path(tmp)
        for question, out_path in pending:
            print(f"generating {question['id']} -> {out_path.relative_to(REPO_ROOT)}")
            references = {
                turn["voice"]: reference_for(binary, model, codec, turn["voice"])
                for turn in question["dialogueScript"]
            }
            turn_paths = []
            for index, turn in enumerate(question["dialogueScript"]):
                turn_path = tmp_dir / f"{question['id']}-{index}.wav"
                synthesize(
                    binary,
                    model,
                    codec,
                    turn["text"],
                    turn["voice"],
                    turn_path,
                    reference=references[turn["voice"]],
                )
                turn_paths.append(turn_path)
            write_dialogue(turn_paths, out_path)

    print(f"Done. Generated {len(pending)} file(s).")


if __name__ == "__main__":
    main()
