# Model and API environment contract

The repository-root `.env` file is the only local file contributors should edit
for cloud model credentials. It is ignored by Git. `.env.example` is the shared,
secret-free contract and must remain safe to commit.

## Setup

```bash
cp .env.example .env
```

Fill these three credentials in `.env`:

```dotenv
MIMO_API_KEY=
QWEN_API_KEY=
GLM_API_KEY=
```

Do not paste keys into `configs/*.yaml`, Open-LLM-VTuber `conf.yaml`, source code,
logs, screenshots, or chat messages.

## Canonical bindings

| Responsibility | Provider/model environment | Credential | Status |
| --- | --- | --- | --- |
| Video-only emotion | `MIMO_MODEL=mimo-v2.5` | `MIMO_API_KEY` | Implemented |
| Audio-only emotion | `MIMO_MODEL=mimo-v2.5` | `MIMO_API_KEY` | Implemented |
| Audio/video fallback | `QWEN_MODEL=qwen3-omni-flash` | `QWEN_API_KEY` | Contract defined; adapter pending |
| Text-only emotion | `GLM_TEXT_EMOTION_MODEL` | `GLM_API_KEY` | Implemented |
| Companion response | `GLM_COMPANION_MODEL` | `GLM_API_KEY` | Open-LLM-VTuber connection configured |
| Speech recognition | `ASR_MODEL=sherpa_onnx_asr` | None | Local |
| Speech synthesis | `TTS_MODEL=piper_tts` | None | Local voice files still required |

`TEXT_EMOTION_TIMEOUT_SECONDS`, `AUDIO_EMOTION_TIMEOUT_SECONDS`, and
`VIDEO_EMOTION_TIMEOUT_SECONDS` control independent Provider latency budgets.
`EMOTION_BACKEND_TIMEOUT_SECONDS` must be longer than the largest of those
budgets so the VTuber adapter can receive the canonical fallback result. A
Provider timeout degrades only that modality and does not discard the others.

MiMo pay-as-you-go uses `https://api.xiaomimimo.com/v1`. MiMo Token Plan keys
use the plan-specific endpoint shown in the MiMo console instead. Qwen endpoints
are region/workspace-specific; replace `QWEN_BASE_URL` when the console provides
a workspace URL. GLM uses `https://open.bigmodel.cn/api/paas/v4`.

The provider/model choices above follow `SSOT.md`. Changing provider bindings is
a product-contract change, not a local `.env` customization.

The action mapping, reliability threshold, modality weights, and current live
integration boundary are documented in `docs/action-text-emotion-fusion.md`.

## Enable MiMo audio/video emotion

Keep cloud analysis disabled while editing the file. After filling the MiMo key,
set:

```dotenv
CAMERA_ENABLED=false
VIDEO_EMOTION_ENABLED=true
AUDIO_EMOTION_ENABLED=true
TEXT_EMOTION_ENABLED=true
```

With `CAMERA_ENABLED=false`, MiMo video returns `disabled` without opening a
device; microphone turns still send raw turn audio to MiMo audio after ASR, and
the transcript independently goes to GLM text emotion.

Then run one explicit paid smoke-test command:

```bash
.venv/bin/python scripts/debug_video_pipeline.py --mode provider --duration 5
```

To test action recognition, text emotion, and final weighted fusion together:

```bash
.venv/bin/python scripts/debug_video_pipeline.py --mode provider --duration 5 \
  --transcript "我今天感觉很好"
```

The test samples up to the configured frame limit and removes temporary media
when `retain_media` is false. Without `--transcript` it makes one MiMo request;
with `--transcript` it additionally makes one GLM text-emotion request.

## Validate and start GLM-backed VTuber

After filling `GLM_API_KEY`, validate without starting a server:

```bash
third_party/Open-LLM-VTuber/.venv/bin/python \
  scripts/start_open_llm_vtuber.py --check-only
```

Start the server on macOS/Linux:

```bash
third_party/Open-LLM-VTuber/.venv/bin/python \
  scripts/start_open_llm_vtuber.py
```

On Windows:

```powershell
.\scripts\start-open-llm-vtuber.ps1 -SkipSync
```

The launcher loads `.env`, keeps `127.0.0.1` binding, and writes only
`${GLM_API_KEY}`-style references to the ignored upstream `conf.yaml`. Existing
process environment values take precedence over `.env` values.

## Local model files still needed

The API configuration does not download licensed or local runtime models. Piper
requires these local files before it can be selected successfully:

```text
third_party/Open-LLM-VTuber/models/piper/zh_CN-huayan-medium.onnx
third_party/Open-LLM-VTuber/models/piper/zh_CN-huayan-medium.onnx.json
third_party/Open-LLM-VTuber/models/piper/zh_CN-chaowen-medium.onnx
third_party/Open-LLM-VTuber/models/piper/zh_CN-chaowen-medium.onnx.json
```
