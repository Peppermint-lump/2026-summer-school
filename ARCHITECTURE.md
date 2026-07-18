# ARCHITECTURE.md

## 1. Scope

This document defines the normative software architecture for Emotion Companion Avatar.

It specifies:

- process boundaries;
- module responsibilities;
- dependency direction;
- data flow;
- security boundaries;
- external-provider boundaries;
- packaging architecture;
- failure and fallback architecture.

Product scope and acceptance criteria are defined in `SSOT.md`.

---

## 2. System context

```text
┌─────────────────────────────────────────────────────────┐
│ Desktop application                                     │
│                                                         │
│  Electron renderer                                      │
│  ├─ Live2D UI                                           │
│  ├─ conversation UI                                     │
│  ├─ settings UI                                         │
│  └─ permission/status UI                                │
│           │                                             │
│           │ allowlisted IPC                             │
│           ▼                                             │
│  Electron main/preload                                  │
│  ├─ backend process lifecycle                           │
│  ├─ OS permissions                                      │
│  ├─ secure settings                                     │
│  └─ loopback endpoint discovery                         │
│           │                                             │
│           │ HTTP/WebSocket on 127.0.0.1                 │
│           ▼                                             │
│  Python backend                                         │
│  ├─ Open-LLM-VTuber adapter                             │
│  ├─ turn manager                                        │
│  ├─ capture coordination                                │
│  ├─ emotion providers                                   │
│  ├─ fusion/conflict                                     │
│  ├─ companion strategy                                  │
│  ├─ GLM response generation                             │
│  └─ TTS/avatar control adapter                          │
└─────────────────────────────────────────────────────────┘
                   │
                   │ HTTPS API calls
                   ▼
┌─────────────────────────────────────────────────────────┐
│ External model providers                                │
│  ├─ MiMo-V2.5                                           │
│  ├─ Qwen3-Omni-Flash                                    │
│  └─ GLM                                                 │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Process architecture

### 3.1 Electron process

Responsibilities:

- application lifecycle;
- main window;
- backend child-process startup/shutdown;
- secure OS-level settings;
- microphone/camera permission flow;
- health polling;
- packaged resource path resolution;
- application update integration if added later.

It must not:

- contain provider API keys in renderer-accessible state;
- perform emotion fusion;
- implement domain decisions;
- directly import Python application logic.

### 3.2 Renderer process

Responsibilities:

- render Live2D;
- display conversation;
- display microphone/camera status;
- display nonclinical emotion-status indicators if enabled;
- collect user settings through safe APIs;
- present privacy disclosures;
- show recoverable errors.

It must not:

- access Node.js directly;
- hold provider credentials;
- read arbitrary local files;
- call cloud providers directly;
- make authoritative conflict decisions.

### 3.3 Python backend process

Responsibilities:

- local application API;
- Open-LLM-VTuber integration;
- VAD/ASR coordination;
- turn lifecycle;
- audio/video processing orchestration;
- provider calls;
- canonical schema translation;
- reliability and conflict computation;
- strategy routing;
- reply generation;
- TTS and avatar-state dispatch;
- media cleanup;
- structured logging.

The packaged backend listens only on loopback.

---

## 4. Repository architecture

```text
emotion-companion-avatar/
├── apps/
│   ├── desktop/
│   │   ├── src/main/
│   │   ├── src/preload/
│   │   ├── src/renderer/
│   │   └── resources/
│   │
│   └── backend/
│       ├── app/
│       │   ├── api/
│       │   ├── capture/
│       │   ├── emotion/
│       │   ├── fusion/
│       │   ├── companion/
│       │   ├── avatar/
│       │   ├── integration/
│       │   ├── infrastructure/
│       │   └── main.py
│       └── tests/
│
├── packages/
│   ├── schemas/
│   └── shared-config/
│
├── third_party/
│   └── Open-LLM-VTuber/
│
├── assets/
│   └── live2d/
│
├── configs/
│   └── prompts/
│
├── scripts/
├── tests/
├── docs/
└── runtime/
```

---

## 5. Backend module boundaries

### 5.1 `api`

Owns:

- local HTTP/WebSocket endpoints;
- request validation;
- response serialization;
- health endpoint;
- configuration endpoint;
- turn status endpoint.

Depends on:

- application services;
- schemas.

Must not depend directly on:

- provider SDKs;
- OpenCV internals;
- Live2D files.

### 5.2 `capture`

Owns:

- `TurnRecord` creation;
- speech-start/speech-end timing;
- audio artifact coordination;
- camera frame buffer coordination;
- video/frames export;
- temporary media lifecycle state.

Submodules:

```text
capture/
├── turn_manager.py
├── audio_capture.py
├── camera_buffer.py
├── video_export.py
└── media_cleanup.py
```

`capture` produces media artifacts but does not classify emotion.

### 5.3 `emotion`

Owns:

- provider interfaces;
- provider implementations;
- prompt loading;
- provider payload conversion;
- canonical `ModalityEmotion` outputs;
- local quality computation.

Structure:

```text
emotion/
├── providers/
│   ├── base.py
│   ├── mimo.py
│   ├── qwen_omni.py
│   └── glm.py
├── audio/
│   ├── preprocess.py
│   ├── quality.py
│   └── service.py
├── video/
│   ├── preprocess.py
│   ├── face_quality.py
│   ├── action_emotion.py
│   └── service.py
└── text/
    ├── quality.py
    └── service.py
```

Rules:

- provider implementations do not know fusion logic;
- audio service does not receive transcript;
- video service does not receive transcript or audio labels;
- standardized actions remain nested video observations and are blended only
  inside the video service with a bounded deterministic weight;
- text service receives transcript only;
- all provider payloads are normalized before leaving `emotion`.

### 5.4 `fusion`

Owns:

- label normalization policy;
- reliability calculation;
- conflict classification;
- conflict score;
- insufficient-evidence rules.

The final label score is a normalized weighted sum of canonical label score,
configured modality weight, and reliability. The fusion layer never treats an
observed action as an independent modality.

Structure:

```text
fusion/
├── reliability.py
├── conflict_detector.py
├── rules.py
└── service.py
```

Depends only on:

- canonical schemas;
- configuration.

Must not depend on:

- provider clients;
- GLM;
- OpenCV;
- Electron;
- Open-LLM-VTuber.

This is the most important pure-domain module and must be highly unit tested.

### 5.5 `companion`

Owns:

- strategy routing;
- reply prompt construction;
- safe-response constraints;
- GLM reply request;
- canonical `CompanionDecision`.

Structure:

```text
companion/
├── strategy_router.py
├── prompt_builder.py
├── response_service.py
└── safety.py
```

`companion` receives a `ConflictResult`; it does not recompute conflict.

### 5.6 `avatar`

Owns:

- mapping `avatar_emotion` to Live2D expression;
- mapping `voice_style` to supported TTS settings;
- dispatching avatar state;
- neutral fallback.

Structure:

```text
avatar/
├── state_mapper.py
├── live2d_adapter.py
└── tts_adapter.py
```

It must not infer user emotion.

### 5.7 `integration`

Owns:

- Open-LLM-VTuber adapter;
- orchestration insertion point between ASR and agent response;
- conversion between upstream types and canonical schemas;
- upstream-patch isolation.

Structure:

```text
integration/
├── open_llm_vtuber_adapter.py
├── emotion_middleware.py
└── conversation_orchestrator.py
```

Direct upstream modifications must be minimized and documented.

### 5.8 `infrastructure`

Owns:

- configuration loading;
- secret storage adapter;
- HTTP client;
- retry policy;
- logging;
- clock;
- filesystem;
- application paths;
- process diagnostics.

Domain modules must not read environment variables directly.

---

## 6. Dependency direction

Normative dependency graph:

```text
Electron renderer
    ↓
Electron preload/main
    ↓
Backend API
    ↓
Conversation orchestrator
    ├───────────────┬────────────────┬────────────────┐
    ↓               ↓                ↓                ↓
Capture        Emotion services    Fusion         Companion
                    ↓                ↓                ↓
              Provider ports     Canonical       GLM reply port
                    ↓             schemas              ↓
              Provider adapters                   GLM adapter
    ↓
Avatar adapters
    ↓
Open-LLM-VTuber / TTS / Live2D
```

Rules:

- inner domain layers never import outer infrastructure;
- provider adapters implement domain ports;
- fusion is provider-agnostic;
- desktop is backend-implementation-agnostic;
- shared schemas do not import SDK types;
- all paths from UI to provider cross backend API and application service boundaries.

---

## 7. Turn lifecycle

Canonical state machine:

```text
IDLE
  ↓ speech_start
CAPTURING
  ↓ speech_end
FINALIZING_MEDIA
  ↓ audio/video ready
TRANSCRIBING
  ↓ transcript ready
ANALYZING_MODALITIES
  ↓ modality results or timeout
FUSING
  ↓ conflict result
SELECTING_STRATEGY
  ↓ strategy
GENERATING_REPLY
  ↓ reply
SYNTHESIZING
  ↓ audio ready
PRESENTING
  ↓ playback complete
CLEANING_UP
  ↓
IDLE
```

Failure may cause modality-specific degradation, not whole-turn cancellation.

Each transition must be traceable by `turn_id`.

---

## 8. Per-turn data flow

```text
microphone
  ↓
VAD + audio capture
  ↓
audio.wav ──────────────┐
                        │
camera                   │
  ↓                      │
timestamped frame buffer │
  ↓                      │
video.mp4 / frames ──────┤
                        │
ASR                      │
  ↓                      │
transcript ──────────────┤
                        ▼
              parallel modality analysis
          ┌────────────┼────────────┐
          ▼            ▼            ▼
     text-only     audio-only    video-only
          └────────────┼────────────┘
                       ▼
                 canonical results
                       ▼
                 reliability/fusion
                       ▼
                 companion strategy
                       ▼
                   GLM reply
                       ▼
                  TTS + avatar
                       ▼
                    cleanup
```

Text, audio, and video analysis should run concurrently after their inputs are ready.

### 8.1 Continuous video-only observation

After explicit camera consent, one backend worker periodically analyzes a bounded
ordered-frame window. It sends neither transcript nor audio to the video provider.
The latest canonical video observation is published to connected VTuber clients,
which update Live2D immediately without waiting for a speech or text turn. The
worker is single-instance, skips overlapping runs, retains no raw frames after
inference, and stops with the backend.

---

## 9. Canonical schemas

### 9.1 TurnRecord

```json
{
  "schema_version": "1.0",
  "session_id": "session_001",
  "turn_id": "turn_000001",
  "speech_start_ms": 1721188801200,
  "speech_end_ms": 1721188805700,
  "audio_path": "runtime/turns/turn_000001/audio.wav",
  "video_path": "runtime/turns/turn_000001/video.mp4",
  "frame_paths": [],
  "transcript": "没事，我今天挺好的。"
}
```

### 9.2 ModalityEmotion

```json
{
  "schema_version": "1.0",
  "modality": "audio",
  "label": "negative",
  "fine_emotion": "subdued",
  "confidence": 0.74,
  "quality": 0.88,
  "reliability": 0.6512,
  "evidence": [
    "语速偏慢",
    "能量偏低"
  ],
  "status": "ok",
  "raw_metadata": {}
}
```

Possible `status`:

```text
ok
uncertain
insufficient_evidence
provider_error
timeout
disabled
```

### 9.3 ConflictResult

```json
{
  "schema_version": "1.0",
  "conflict": true,
  "conflict_type": "verbal_positive_behavior_negative",
  "conflict_score": 0.72,
  "reliable_modalities": [
    "text",
    "audio",
    "video"
  ],
  "strategy": "gentle_check_in",
  "explanation": "文本表达积极，可靠的语音和视觉信号偏消极。"
}
```

### 9.4 CompanionDecision

```json
{
  "schema_version": "1.0",
  "reply": "你说自己还好，不过听起来好像有点疲惫。今天是不是消耗比较大？不想展开说也没关系。",
  "strategy": "gentle_check_in",
  "avatar_emotion": "neutral",
  "voice_style": "gentle"
}
```

---

## 10. External provider architecture

Define ports:

```python
class AudioEmotionProvider(Protocol):
    async def analyze_audio(self, request: AudioEmotionRequest) -> ModalityEmotion:
        ...

class VideoEmotionProvider(Protocol):
    async def analyze_video(self, request: VideoEmotionRequest) -> ModalityEmotion:
        ...

class TextEmotionProvider(Protocol):
    async def analyze_text(self, request: TextEmotionRequest) -> ModalityEmotion:
        ...

class CompanionModelProvider(Protocol):
    async def generate_reply(self, request: CompanionRequest) -> CompanionDecision:
        ...
```

Default bindings:

```text
AudioEmotionProvider -> MiMo
VideoEmotionProvider -> MiMo
TextEmotionProvider  -> GLM
CompanionModelProvider -> GLM
```

Fallback bindings:

```text
AudioEmotionProvider -> Qwen3-Omni-Flash
VideoEmotionProvider -> Qwen3-Omni-Flash
```

Provider selection is configuration-driven.

Provider adapters must implement:

- timeout;
- retry;
- schema validation;
- malformed-output recovery;
- rate-limit mapping;
- usage logging without content leakage.

---

## 11. Prompt architecture

Prompts are versioned files:

```text
configs/prompts/
├── audio_emotion_v1.txt
├── video_emotion_v1.txt
├── text_emotion_v1.txt
└── companion_response_v1.txt
```

Rules:

- prompt version is logged;
- audio prompt explicitly forbids lexical-semantic inference;
- video prompt explicitly forbids transcript/audio inference;
- text prompt explicitly limits analysis to literal text;
- companion prompt receives canonical observations and strategy, not raw media;
- provider adapters do not embed unrelated product policy in code.

---

## 12. Security architecture

### 12.1 Trust boundaries

```text
Untrusted:
- microphone input
- camera input
- ASR text
- provider responses
- imported configuration
- downloaded model assets

Trusted application domain:
- validated canonical schemas
- deterministic fusion rules
- strategy router

External:
- MiMo
- Qwen
- GLM
```

All external responses must be schema-validated.

### 12.2 Desktop isolation

Required Electron settings:

- `contextIsolation: true`;
- `nodeIntegration: false`;
- restrictive Content Security Policy;
- explicit preload bridge;
- allowlisted IPC;
- no secrets in renderer;
- no arbitrary shell execution from renderer;
- no remote module.

### 12.3 Backend exposure

Packaged app backend:

```text
host = 127.0.0.1
port = dynamically selected or configurable local port
```

Do not expose on LAN by default.

If a session token is used for local API protection, it must be generated at startup and passed securely to the desktop main process.

### 12.4 Media path safety

- use application-owned runtime directories;
- reject path traversal;
- generate filenames server-side;
- validate MIME and actual media type;
- cap file size and duration;
- remove temporary files on success, failure, and shutdown.

### 12.5 Secret storage

Development:

- `.env` outside version control.

Packaged application:

- OS keychain/credential store preferred;
- encrypted application settings acceptable only with documented limitations;
- never renderer localStorage.

---

## 13. Privacy architecture

Default data lifecycle:

```text
capture
→ temporary local media
→ provider upload
→ canonical result
→ delete local temporary media
```

Logs contain:

- turn ID;
- stage;
- status;
- latency;
- provider;
- token/usage counts;
- quality and normalized labels when configured.

Logs do not contain:

- base64 media;
- raw frames;
- raw audio;
- full conversation text by default;
- API keys.

A debug-retention flag changes retention only, not logging policy.

---

## 14. Failure architecture

### 14.1 Failure categories

```text
capture_error
asr_error
provider_timeout
provider_rate_limit
provider_invalid_output
insufficient_evidence
tts_error
avatar_error
backend_startup_error
```

### 14.2 Fallback policy

```text
text unavailable
-> ask user to repeat or use remaining modalities only for nonverbal observation;
   do not generate a semantic reply without a valid user utterance

audio emotion unavailable
-> continue text + video

video unavailable
-> continue text + audio

both nonverbal unavailable
-> normal text conversation

companion provider unavailable
-> present recoverable error; optional fallback model if configured

TTS unavailable
-> display text reply

avatar unavailable
-> preserve conversation functionality
```

### 14.3 Time budget

Suggested initial budgets:

```text
ASR:                configurable, target < 2 s after speech end
audio emotion API:  15 s timeout
video emotion API:  20 s timeout
text emotion API:   10 s timeout
reply generation:   30 s timeout
```

The UI must expose progress without displaying misleading emotion conclusions.

---

## 15. Concurrency architecture

After ASR and media finalization:

```text
audio emotion ┐
video emotion ├─ run concurrently
text emotion  ┘
```

Use bounded concurrency and cancellation.

When the overall emotion deadline expires:

- collect completed modality results;
- mark incomplete results as timeout;
- continue fusion with available reliable modalities;
- never wait indefinitely.

Only one authoritative orchestration coroutine owns a turn.

---

## 16. Open-LLM-VTuber integration

Canonical insertion point:

```text
VAD speech end
→ ASR transcript
→ EmotionMiddleware.analyze_turn()
→ ConflictResult
→ Companion response generation
→ TTS
→ Live2D
```

The emotion pipeline is mandatory middleware when enabled, not an optional LLM tool.

Adapter responsibilities:

- subscribe to or wrap the ASR completion point;
- construct `TurnRecord`;
- call orchestration service;
- inject canonical companion decision;
- map reply and avatar state to upstream mechanisms.

Avoid changes to unrelated upstream behavior.

---

## 17. Live2D architecture

Runtime avatar state:

```text
neutral
joy
affection
sadness
anger
sleepy
blush
```

The avatar mapper translates canonical states to model expressions.

Conflict scenarios default to neutral or mild concern behavior. They must not automatically trigger strong crying or anger expressions.

Special motions are separate from emotion states.

Canonical visual-event motions are deterministic and bounded: `wave` may select
`greeting`, while a high-confidence non-still action without an authored motion may
select the neutral `observe` fallback. `observe` must preserve the selected expression, must not trigger a
companion reply, and yields to authored special motions before returning to Idle.

The Idle motion remains active where supported because it drives crying/sleepy loop parameters.

---

## 18. Desktop startup and shutdown

Startup:

```text
Electron main starts
→ resolve packaged backend path
→ allocate loopback port
→ create ephemeral local session token
→ spawn backend
→ poll /health
→ open renderer
→ load avatar and settings
```

Shutdown:

```text
renderer closes
→ main requests backend shutdown
→ wait bounded interval
→ terminate child if necessary
→ backend cleanup handler removes temporary media
→ application exits
```

A stale backend process is a release-blocking bug.

---

## 19. Packaging architecture

### Windows

Artifacts:

```text
EmotionCompanion-Setup.exe
```

Optional:

```text
portable.exe
msi
```

Bundled:

- Electron application;
- Python backend executable;
- FFmpeg binary;
- frontend assets;
- configuration templates;
- permitted Live2D runtime assets.

### macOS

Primary artifact:

```text
EmotionCompanion-arm64.dmg
```

Requirements:

- microphone usage description;
- camera usage description;
- hardened runtime/signing plan for distribution;
- notarization for public distribution;
- packaged backend built on macOS.

Cross-platform rule:

- build platform-specific Python binaries on the target OS;
- do not assume Windows-produced binaries run on macOS;
- keep filesystem paths and process launching platform-aware.

---

## 20. Configuration architecture

Configuration precedence:

```text
built-in defaults
< packaged config
< user config
< environment variables
< command-line arguments
```

Configuration categories:

- provider selection;
- API endpoint;
- model names;
- timeouts;
- reliability threshold;
- capture settings;
- retention policy;
- avatar mapping;
- TTS settings;
- logging level.

Secrets are referenced, not stored in ordinary YAML committed to Git.

---

## 21. Observability

Per-turn trace:

```text
turn_created
audio_ready
video_ready
asr_complete
text_emotion_complete
audio_emotion_complete
video_emotion_complete
fusion_complete
strategy_selected
reply_complete
tts_complete
presentation_complete
cleanup_complete
```

Metrics:

- stage latency;
- provider success rate;
- schema failure rate;
- timeout rate;
- modality quality distribution;
- conflict-type distribution;
- fallback frequency;
- temporary-media cleanup failures.

Do not use observability to retain sensitive content by default.

---

## 22. Architectural constraints for future work

Future capabilities may be added only if they preserve current boundaries.

Examples:

- local Omni provider implements existing provider ports;
- WebRTC streaming adds a capture transport without bypassing canonical schemas;
- persistent memory belongs in a separate consented subsystem;
- trainable fusion replaces `fusion` internals but preserves `ConflictResult`;
- new avatar models implement `AvatarAdapter`.

Do not introduce future capabilities by coupling domain logic directly to a new provider or UI.
