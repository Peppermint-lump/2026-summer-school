# AGENTS.md

## 1. Purpose

This repository implements a desktop AI companion avatar with:

- real-time voice interaction;
- Live2D rendering and expression control;
- per-turn audio and video capture;
- independent text, audio, and visual emotion analysis;
- cross-modal emotion consistency and conflict detection;
- strategy-aware companion response generation;
- Windows and macOS desktop packaging.

This file defines how Codex and human contributors must modify the repository.

The normative product definition is in `SSOT.md`.
The normative dependency and module design is in `ARCHITECTURE.md`.

When documents conflict, use this precedence:

1. `SSOT.md`
2. `ARCHITECTURE.md`
3. `AGENTS.md`
4. implementation comments and existing code

Do not silently reinterpret product scope.

---

## 2. Non-negotiable engineering rules

### 2.1 Preserve modality independence

Text, audio, and video emotion analysis must remain logically independent.

Allowed:

```text
ASR transcript -> text-only emotion analysis
raw audio      -> audio-only emotion analysis
video/frames   -> video-only emotion analysis
```

Forbidden:

- passing transcript to the audio-emotion prompt;
- passing transcript or audio results to the video-emotion prompt;
- using the final companion model to fabricate missing modality labels;
- treating a joint multimodal answer as equivalent to three independently observed modalities.

A joint multimodal call may exist only as an optional experiment. It must not replace the canonical independent-analysis pipeline.

### 2.2 Models observe; deterministic code decides conflict

Model providers return modality observations.

Deterministic application code must compute:

- normalized label;
- input quality;
- modality reliability;
- conflict type;
- conflict score;
- fallback behavior;
- companion strategy.

Do not delegate the authoritative conflict decision to a free-form LLM response.

### 2.3 Emotion inference is weak evidence

The system must never claim that it knows the user's internal state.

Forbidden response patterns include:

- “你明明很难过”
- “你在隐藏情绪”
- “我看得出你患有……”
- diagnosis, treatment, or medical claims based on model inference;
- coercive questioning.

The companion must use uncertainty-aware language and permit the user not to elaborate.

### 2.4 Fail open to normal conversation

Failure of one modality must not terminate the conversation.

Required degradation:

```text
video unavailable     -> continue with text + audio
audio emotion failure -> continue with text + video
emotion API timeout   -> continue with normal text conversation
camera disabled       -> do not request visual inference
insufficient evidence -> do not report strong conflict
```

### 2.5 Raw media is temporary by default

Raw microphone and camera data is sensitive.

Default behavior:

- store media only for the active turn;
- delete temporary media after inference;
- retain media only when explicit debug/consent configuration is enabled;
- never commit raw media to Git;
- never place raw media in application logs;
- never expose local media paths to end users unless required for diagnostics.

### 2.6 API keys and credentials

Secrets must be loaded from user configuration, environment variables, or OS credential storage.

Forbidden:

- hard-coded API keys;
- committing `.env`;
- embedding production keys into packaged binaries;
- logging authorization headers;
- including secrets in exception traces.

### 2.7 Third-party code boundary

`third_party/Open-LLM-VTuber/` is pinned third-party code.

Prefer:

1. adapters;
2. wrappers;
3. narrowly scoped patches;
4. documented patch files.

Do not broadly rewrite the upstream project.

Any direct modification must include:

- reason;
- upstream file and function;
- expected behavior;
- regression test or reproducible validation;
- note in `docs/upstream-patches.md` if that file exists.

### 2.8 Purchased Live2D assets

Purchased Live2D files are private assets.

Forbidden:

- committing original or modified model files to a public repository;
- renaming or redistributing licensed assets without checking the license;
- modifying the original backup copy;
- bundling assets into public releases unless the license permits it.

Development must use:

```text
assets/live2d/xiaohudie-original/  # immutable local backup
assets/live2d/xiaohudie-runtime/   # local working copy
```

Both directories must be ignored by Git unless the project owner explicitly states otherwise.

---

## 3. Repository ownership and dependency direction

Expected top-level structure:

```text
apps/
  desktop/        Electron desktop shell
  backend/        Python application backend
packages/
  schemas/        shared versioned data contracts
  shared-config/  shared configuration definitions
third_party/
  Open-LLM-VTuber/
assets/
  live2d/
configs/
tests/
scripts/
docs/
runtime/
```

Allowed dependency direction:

```text
desktop -> backend HTTP/WebSocket API
backend integration -> domain services
domain services -> provider interfaces
provider implementations -> external APIs
fusion -> schemas only
policy -> fusion results + schemas
third_party adapter -> third_party code
```

Forbidden dependency direction:

```text
fusion -> MiMo/Qwen/GLM SDK
video pipeline -> audio pipeline internals
audio pipeline -> video pipeline internals
domain schemas -> provider-specific payloads
desktop renderer -> Python implementation modules
provider client -> Live2D controller
```

No circular imports between `capture`, `emotion`, `fusion`, `companion`, and `integration`.

---

## 4. Canonical domain objects

Do not create competing ad hoc dictionaries when a shared schema exists.

Minimum canonical objects:

- `TurnRecord`
- `ModalityEmotion`
- `ConflictResult`
- `CompanionDecision`
- `AvatarState`
- `ProviderHealth`
- `AppConfig`

All external-provider payloads must be translated into canonical schemas at the provider boundary.

Provider-specific fields belong in a namespaced `raw_metadata` field and must not leak into fusion logic.

---

## 5. Coding rules

### Python

- Python 3.11 target.
- Use type annotations for public functions.
- Use Pydantic models or dataclasses for domain contracts.
- Use `pathlib.Path`, not string path concatenation.
- Use async I/O for network calls.
- Every external request must have:
  - timeout;
  - bounded retry;
  - structured error mapping;
  - cancellation support where practical.
- Do not use broad `except Exception` without re-raising or converting to a typed application error.
- Keep provider prompts in configuration files, not inline across multiple modules.
- Keep fusion thresholds in configuration, not scattered constants.

### TypeScript / Electron

- Use strict TypeScript.
- Keep Electron main process, preload, and renderer responsibilities separate.
- Enable context isolation.
- Do not expose unrestricted Node.js APIs to the renderer.
- IPC must use explicit allowlisted channels.
- Do not pass API keys to the renderer process.
- The desktop app must communicate with the backend over loopback only.

### Logging

Logs must include correlation identifiers:

```text
session_id
turn_id
request_id
provider
stage
latency_ms
status
```

Do not log:

- raw audio;
- raw video frames;
- full provider authorization data;
- complete personal conversations by default;
- face images;
- base64 media.

Use redacted summaries.

---

## 6. Required development workflow

Before changing code:

1. Read `SSOT.md`.
2. Read the relevant section of `ARCHITECTURE.md`.
3. Identify the owning module.
4. Confirm whether the change affects a public schema.
5. Confirm whether the change crosses a security or privacy boundary.
6. State the expected behavior and acceptance criteria.

During implementation:

1. Make the smallest coherent change.
2. Preserve dependency direction.
3. Add or update tests.
4. Update configuration examples.
5. Update architecture or SSOT only when the agreed product contract changes.

After implementation:

Run at least:

```text
formatting
static type checks
unit tests
schema compatibility tests
targeted integration tests
secret scan
```

For changes affecting capture, providers, fusion, or packaging, also run the relevant end-to-end smoke test.

---

## 7. Testing requirements

### Mandatory unit-test areas

- label normalization;
- reliability calculation;
- conflict classification;
- insufficient-evidence handling;
- provider timeout and retry;
- media cleanup;
- schema validation;
- strategy routing;
- avatar-state mapping.

### Mandatory integration scenarios

1. Consistent positive:
   - text positive;
   - audio positive;
   - video positive.

2. Verbal-positive / behavioral-negative:
   - text positive;
   - reliable audio negative;
   - reliable video negative.

3. Video unavailable:
   - camera disabled or no valid face;
   - system continues with remaining modalities.

4. Emotion provider timeout:
   - ordinary conversation still completes.

5. Low-quality audio:
   - audio reliability below threshold;
   - no strong audio-driven conflict.

6. User disables media retention:
   - temporary files are removed after processing.

7. Backend startup failure:
   - desktop displays a clear recoverable error.

8. App shutdown:
   - child backend process terminates;
   - temporary media cleanup runs.

### Tests must not require paid API calls by default

Use fixtures and fake provider implementations.

Paid-provider smoke tests must be opt-in and explicitly marked.

---

## 8. Forbidden implementation shortcuts

Do not:

- use the chat model's final reply as the text-emotion label;
- infer video emotion from a single arbitrary frame;
- treat provider self-reported confidence as calibrated probability;
- classify conflict when fewer than two reliable modalities exist;
- block the entire reply on nonessential emotion analysis;
- expose the backend on `0.0.0.0` in the packaged desktop app;
- store API keys in localStorage;
- put Python virtual environments inside packaged application data;
- require the end user to install Python, Node.js, FFmpeg, or Git;
- commit generated runtime files;
- introduce a database before persistence requirements justify it;
- add full-duplex streaming before the per-turn pipeline is stable;
- add user memory or psychological profiling in the MVP;
- change model providers without preserving the canonical provider interface.

---

## 9. Definition of done

A task is done only when:

- behavior matches `SSOT.md`;
- dependency direction matches `ARCHITECTURE.md`;
- tests pass;
- failure and fallback behavior are covered;
- logs contain no sensitive payloads;
- public schemas are versioned or backward-compatible;
- configuration examples are updated;
- Windows behavior is validated when the change affects the MVP;
- macOS-specific behavior is documented when relevant.

---

## 10. Codex-specific instructions

When asked to implement a feature:

- inspect existing code before proposing new files;
- do not invent APIs that are not present;
- do not modify unrelated modules;
- provide a concise implementation plan before broad changes;
- surface uncertainty instead of guessing;
- stop and ask when a requested change violates `SSOT.md`;
- preserve user-owned media and licensed assets;
- do not run destructive commands without explicit approval;
- do not rewrite lockfiles unless dependencies changed;
- do not upgrade Open-LLM-VTuber or core model providers implicitly;
- do not change packaging targets or minimum OS versions without approval.

When multiple valid designs exist, prefer the one with:

1. clearer dependency boundaries;
2. easier offline testing;
3. safer media handling;
4. simpler fallback behavior;
5. lower packaging risk.
