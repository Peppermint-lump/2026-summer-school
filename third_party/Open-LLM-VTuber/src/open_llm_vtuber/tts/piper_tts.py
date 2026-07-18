import subprocess
import sys
from pathlib import Path

from loguru import logger

from .tts_interface import TTSInterface


class TTSEngine(TTSInterface):
    """Local Piper TTS adapter invoked through the active Python environment."""

    def __init__(self, model_path: str, timeout_seconds: int = 60):
        self.model_path = Path(model_path)
        self.timeout_seconds = timeout_seconds

    def generate_audio(self, text: str, file_name_no_ext: str | None = None) -> str:
        if not self.model_path.is_file():
            raise FileNotFoundError(
                f"Piper model not found: {self.model_path}. "
                "Download the configured .onnx voice model and its matching .onnx.json file."
            )
        config_path = self.model_path.with_suffix(self.model_path.suffix + ".json")
        if not config_path.is_file():
            raise FileNotFoundError(
                f"Piper voice configuration not found: {config_path}. "
                "Download the matching .onnx.json file for the configured voice model."
            )

        output_path = Path(self.generate_cache_file_name(file_name_no_ext, "wav"))
        command = [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "piper",
            "--model",
            str(self.model_path),
            "--output_file",
            str(output_path),
        ]

        try:
            completed = subprocess.run(
                command,
                input=text,
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Piper synthesis timed out after {self.timeout_seconds} seconds."
            ) from exc

        if completed.returncode != 0 or not output_path.is_file():
            error = completed.stderr.strip() or "Piper did not produce a WAV file."
            raise RuntimeError(f"Piper synthesis failed: {error}")

        logger.info("Piper generated local audio: {}", output_path.name)
        return str(output_path)
