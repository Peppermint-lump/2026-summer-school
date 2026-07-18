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

It is intentionally ignored by Git. Provider secrets belong only in the
repository-root `.env`; the generated config contains environment references,
not credential values. See `docs/model-api-configuration.md`.

## Run in development

Install `uv` first if it is not already available on PATH. In this workspace, a local copy may also exist at:

```text
.tools/uv/bin/uv.exe
```

Then run:

```powershell
.\scripts\start-open-llm-vtuber.ps1
```

On macOS/Linux, validate and start through the environment-aware adapter:

```bash
third_party/Open-LLM-VTuber/.venv/bin/python scripts/start_open_llm_vtuber.py --check-only
third_party/Open-LLM-VTuber/.venv/bin/python scripts/start_open_llm_vtuber.py
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
