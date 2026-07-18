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
        raise ValueError("Felix must register neutral, 22 supplied presets, and 2 combined presets")

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

    default_voice = default_character["tts_config"]["piper_tts"]["model_path"]
    felix_voice = felix_character["tts_config"]["piper_tts"]["model_path"]
    if default_voice == felix_voice:
        raise ValueError("Felix and Xiaohudie must use isolated Piper voices")
    felix_voice_path = VTUBER_ROOT / felix_voice
    if not felix_voice_path.is_file():
        raise FileNotFoundError(f"Missing Felix Piper model: {felix_voice_path}")
    felix_voice_config = felix_voice_path.with_suffix(
        felix_voice_path.suffix + ".json"
    )
    if not felix_voice_config.is_file():
        raise FileNotFoundError(
            f"Missing Felix Piper voice configuration: {felix_voice_config}"
        )

    print(
        "Felix validation passed: "
        f"{len(expression_names)} expressions, "
        f"{len(felix_model['emotionMap'])} emotion tags, isolated Piper voice"
    )


if __name__ == "__main__":
    main()
