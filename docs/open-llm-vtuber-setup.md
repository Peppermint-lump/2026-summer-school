# Open-LLM-VTuber base setup

This project uses Open-LLM-VTuber as a pinned third-party foundation, not as the canonical emotion-fusion implementation.

## Local checkout

The base is located at:

```text
third_party/Open-LLM-VTuber/
```

It is pinned to Open-LLM-VTuber `v1.2.1`.

The upstream frontend submodule is initialized at:

```text
third_party/Open-LLM-VTuber/frontend/
```

## Local configuration

The local runtime config is:

```text
third_party/Open-LLM-VTuber/conf.yaml
```

It is intentionally ignored by Git because it may contain local provider settings and secrets. The current generated config is based on `config_templates/conf.default.yaml` with the server host changed to `127.0.0.1`.

## Run in development

Install `uv` first if it is not already available on PATH. In this workspace, a local copy may also exist at:

```text
.tools/uv/bin/uv.exe
```

Then run:

```powershell
.\scripts\start-open-llm-vtuber.ps1
```

The default development endpoint is:

```text
http://127.0.0.1:12393
```

On first startup, the default `sherpa_onnx_asr` setting may download the SenseVoice model into:

```text
third_party/Open-LLM-VTuber/models/
```

That directory is ignored by Git.

## Integration boundary

Do not add project emotion logic directly inside the upstream checkout. The canonical insertion point for this product is:

```text
VAD speech end
-> ASR transcript
-> EmotionMiddleware.analyze_turn()
-> ConflictResult
-> Companion response generation
-> TTS
-> Live2D
```

Future integration code belongs under `apps/backend/app/integration/`.
