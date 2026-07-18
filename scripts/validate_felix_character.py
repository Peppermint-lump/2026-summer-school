from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
VTUBER_ROOT = ROOT / "third_party" / "Open-LLM-VTuber"
RUNTIME = VTUBER_ROOT / "live2d-models" / "felix" / "runtime"


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    model_file = RUNTIME / "wd66.model3.json"
    model = load_json(model_file)
    references = model["FileReferences"]

    required_files = [
        references["Moc"],
        references["Physics"],
        references["DisplayInfo"],
        *references["Textures"],
        *(entry["File"] for entry in references["Expressions"]),
    ]
    missing = [name for name in required_files if not (RUNTIME / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing Felix runtime files: {missing}")

    expression_names = [entry["Name"] for entry in references["Expressions"]]
    if len(expression_names) != 25 or len(set(expression_names)) != 25:
        raise ValueError(
            "Felix must register neutral, 22 supplied presets, and 2 combined presets"
        )

    groups = {group["Name"]: group["Ids"] for group in model["Groups"]}
    if groups.get("LipSync") != ["ParamMouthOpenY"]:
        raise ValueError("Felix LipSync must use ParamMouthOpenY")

    model_dict = load_json(VTUBER_ROOT / "model_dict.json")
    default_config = yaml.safe_load(
        (VTUBER_ROOT / "conf.yaml").read_text(encoding="utf-8-sig")
    )
    felix_config = yaml.safe_load(
        (VTUBER_ROOT / "characters" / "felix.yaml").read_text(encoding="utf-8")
    )
    felix_model = next(item for item in model_dict if item["name"] == "felix")
    expression_count = len(expression_names)
    invalid_indices = {
        key: value
        for key, value in felix_model["emotionMap"].items()
        if not isinstance(value, int) or not 0 <= value < expression_count
    }
    if invalid_indices:
        raise ValueError(f"Invalid Felix emotion indices: {invalid_indices}")

    default_character = default_config["character_config"]
    felix_character = felix_config["character_config"]
    if default_character["live2d_model_name"] != "xiaohudie":
        raise ValueError("Xiaohudie must remain the startup default")
    if felix_character["conf_uid"] != "felix_001":
        raise ValueError("Felix must use its isolated felix_001 configuration")
    if felix_character["persona_prompt"] == default_character["persona_prompt"]:
        raise ValueError("Felix and Xiaohudie personas must remain isolated")

    default_tts = default_character["tts_config"]
    felix_tts = felix_character["tts_config"]
    if default_tts["tts_model"] != "qwen3_tts_realtime":
        raise ValueError("Xiaohudie must use Qwen3 realtime TTS")
    if felix_tts["tts_model"] != "qwen3_tts_realtime":
        raise ValueError("Felix must use Qwen3 realtime TTS")

    default_qwen = default_tts["qwen3_tts_realtime"]
    felix_qwen = felix_tts["qwen3_tts_realtime"]
    if default_qwen["voice"] != "Cherry":
        raise ValueError("Xiaohudie must use the Cherry Qwen voice")
    if felix_qwen["voice"] != "Ethan":
        raise ValueError("Felix must use the Ethan Qwen male voice")

    default_fallback = default_qwen["fallback_model_path"]
    felix_fallback = felix_qwen["fallback_model_path"]
    if default_fallback == felix_fallback:
        raise ValueError("Felix and Xiaohudie must use isolated Piper fallbacks")
    for fallback in (default_fallback, felix_fallback):
        model_path = VTUBER_ROOT / fallback
        if not model_path.is_file():
            raise FileNotFoundError(f"Missing Piper fallback model: {model_path}")
        config_path = model_path.with_suffix(model_path.suffix + ".json")
        if not config_path.is_file():
            raise FileNotFoundError(
                f"Missing Piper fallback configuration: {config_path}"
            )

    print(
        "Felix validation passed: "
        f"{len(expression_names)} expressions, "
        f"{len(felix_model['emotionMap'])} emotion tags, isolated Qwen voices, "
        "isolated Piper fallbacks"
    )


if __name__ == "__main__":
    main()
