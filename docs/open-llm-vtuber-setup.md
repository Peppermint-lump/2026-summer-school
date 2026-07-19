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

The same launcher also starts the authenticated canonical emotion middleware at
`http://127.0.0.1:18765`. Its token is generated per process and passed only via
the child-process environment. Set `CAMERA_ENABLED=false` to keep the camera
closed; audio and text turns continue normally.

When `CAMERA_ENABLED=true`, `VIDEO_EMOTION_ENABLED=true`, and
`VIDEO_CONTINUOUS_ENABLED=true`, the launcher automatically starts independent
video-only analysis. No microphone, text message, preview click, or analysis
button is required. The browser “直播” pane is only a local preview.

Metadata-only per-turn traces are written to:

```text
runtime/debug/emotion_turns/<turn_id>/
```

For live browser diagnostics, `window.__lastEmotionAnalysis` contains the most
recent canonical result and `window.__lastAvatarState` contains the dispatched
Live2D state. Neither object contains raw media or credentials.

On first startup, the default `sherpa_onnx_asr` setting may download the SenseVoice model into:

```text
third_party/Open-LLM-VTuber/models/
```

That directory is ignored by Git.

## Text-to-speech

The primary provider is Alibaba Model Studio `qwen3-tts-flash-realtime`. Keep its
API key out of YAML and expose it to the server process as:

```powershell
$env:DASHSCOPE_API_KEY = 'your-api-key'
```

Restart Open-LLM-VTuber after setting the variable. If the key is absent or the
realtime WebSocket request fails, TTS automatically falls back to local Piper.
Xiaohudie uses `zh_CN-huayan-medium`; Felix uses `zh_CN-chaowen-medium`.

Xiaohudie uses the Qwen female voice ID `Cherry`; Felix overrides it with the
male voice ID `Ethan`. Change Xiaohudie's `voice` in `conf.yaml` and Felix's
override in `characters/felix.yaml` if the selected voices change later.

For interactive companion chat, the Zhipu configuration enables GLM thinking
while bounding the time to the first visible response. These settings live under
`character_config.agent_config.llm_configs.zhipu_llm`:

```yaml
thinking_mode: 'enabled'
request_timeout_seconds: 30
first_response_timeout_seconds: 60
max_retries: 1
```

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

Canonical orchestration remains under `apps/backend/app/integration/`; the
upstream checkout contains only the documented loopback and frontend adapters.
