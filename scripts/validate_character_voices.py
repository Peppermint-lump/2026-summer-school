from __future__ import annotations

import os
import sys
import uuid
import wave
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VTUBER_ROOT = ROOT / "third_party" / "Open-LLM-VTuber"
sys.path.insert(0, str(VTUBER_ROOT / "src"))

from open_llm_vtuber.tts.piper_tts import TTSEngine  # noqa: E402


VOICES = {
    "xiaohudie": "models/piper/zh_CN-huayan-medium.onnx",
    "felix": "models/piper/zh_CN-chaowen-medium.onnx",
}


def main() -> None:
    os.chdir(VTUBER_ROOT)
    for character, relative_model in VOICES.items():
        engine = TTSEngine(relative_model, timeout_seconds=60)
        output_path: Path | None = None
        try:
            output_path = Path(
                engine.generate_audio(
                    "你好，我是菲力克斯。很高兴认识你。",
                    f"voice_smoke_{character}_{uuid.uuid4().hex}",
                )
            )
            with wave.open(str(output_path), "rb") as wav_file:
                duration = wav_file.getnframes() / wav_file.getframerate()
                if duration <= 0 or wav_file.getnchannels() <= 0:
                    raise ValueError(f"{character} generated an empty WAV file")
                print(
                    f"{character}: sample_rate={wav_file.getframerate()} "
                    f"duration={duration:.2f}s"
                )
        finally:
            if output_path and output_path.exists():
                output_path.unlink()


if __name__ == "__main__":
    main()
