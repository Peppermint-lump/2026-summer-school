# SSOT.md

## 1. Document status

This document is the single source of truth for product scope and acceptance criteria.

It freezes:

- product goal;
- target users and application scenarios;
- MVP behavior;
- model responsibilities;
- data and privacy boundaries;
- packaging goals;
- prohibited scope expansion.

Implementation must not contradict this document.

---

## 2. Product name

Working name:

```text
Emotion Companion Avatar
```

Chinese description:

```text
基于跨模态情绪冲突检测的 AI 陪伴型数字人
```

The final public name may change without altering product scope.

---

## 3. Product goal

Build a desktop companion-avatar application that:

1. accepts microphone and camera input;
2. conducts natural voice conversation;
3. renders a Live2D character with lip sync and expressions;
4. independently analyzes textual, vocal, and visual emotional signals;
5. detects reliable cross-modal emotional inconsistencies;
6. converts the result into a safe companion strategy;
7. generates an uncertainty-aware response;
8. degrades gracefully when a modality or provider is unavailable.

The central contribution is not merely multimodal emotion recognition.

The central contribution is:

> preserving independent modality observations, explicitly detecting emotion consistency and conflict, and using that conflict to improve a companion avatar's interaction strategy.

---

## 4. Target scenarios

Primary:

- daily conversational companionship;
- AI VTuber / interactive avatar demonstration;
- multimodal affective-computing project demonstration;
- non-diagnostic emotional check-in;
- educational or competition prototype.

Secondary:

- virtual customer service;
- digital human research;
- accessible conversational interfaces.

Out of scope:

- medical diagnosis;
- psychotherapy;
- suicide-risk determination;
- law-enforcement profiling;
- covert surveillance;
- employee or student emotional scoring;
- high-stakes decisions based on inferred emotion.

---

## 5. Canonical user experience

The user launches a desktop application.

The application:

1. starts the local backend;
2. requests microphone permission;
3. optionally requests camera permission;
4. loads the Live2D avatar;
5. waits for the user to speak;
6. creates one interaction turn from speech start to speech end;
7. obtains:
   - ASR transcript;
   - audio-only emotion observation;
   - video-only emotion observation;
   - text-only emotion observation;
8. computes modality reliability;
9. detects consistency or conflict;
10. selects a companion strategy;
11. generates a reply;
12. plays TTS;
13. drives Live2D lip sync and expression;
14. removes temporary media unless retention is explicitly enabled.

The application must remain usable when the camera is disabled.

---

## 6. MVP platform targets

### Required

- Windows desktop application.
- Windows installer or portable desktop build.
- Windows is the reference development and demonstration platform.

### Targeted after Windows stabilization

- macOS desktop application.
- Apple Silicon build is the first macOS target.
- Intel macOS support is optional unless required by the team.

The MVP is not considered blocked by incomplete macOS packaging if the Windows desktop product and macOS development mode both work.

---

## 7. Frozen MVP technology choices

### Desktop and avatar

- Electron desktop shell.
- Open-LLM-VTuber v1.2.1 as the digital-human foundation.
- Live2D “小蝴蝶” model as the default avatar asset.
- Live2D “Felix / 菲力克斯” model as a selectable second avatar with an isolated character persona.
- Local loopback backend service.
- Python 3.11 backend.
- `uv` for Python dependency management.
- FFmpeg for media conversion.
- OpenCV for camera capture and frame processing.

### Speech and conversation

- Open-LLM-VTuber VAD and ASR path.
- SenseVoice / sherpa-onnx as the initial ASR stack.
- Local Piper TTS with a bundled Chinese voice model for the first functional version.
- GLM API for:
  - text-only emotion classification;
  - companion reply generation.

### Multimodal emotion

Default provider:

- MiMo-V2.5 API:
  - audio-only analysis;
  - video-only analysis.

Fallback and comparison provider:

- Qwen3-Omni-Flash.

### Fusion

- deterministic Python rules;
- configurable reliability threshold;
- no trainable fusion model in the MVP.

These choices may be changed only through an explicit product decision and corresponding SSOT update.

---

## 8. Live2D frozen configuration

The runtime copy of the “小蝴蝶” model must include:

- expressions 1–7 registered in `model3.json`;
- motion groups:
  - `Idle`;
  - `Greeting`;
  - `CatchButterfly`;
  - `HoldBear`;
- lip-sync parameter:
  - `ParamMouthOpenY`;
- eye-blink parameters:
  - `ParamEyeROpen`;
  - `ParamEyeLOpen`.

The Idle motion is required because it drives the crying and sleepy loop parameters.

Xiaohudie special motions must remain visible for their complete presentation window:

- `Greeting`: 5 seconds;
- `CatchButterfly`: 6 seconds;
- `HoldBear`: 3 seconds.

Natural completion must transition back to the captured standing baseline over 500 ms before restarting `Idle`. A newer special-motion request may interrupt this transition and replace the previous motion immediately.

The local scene background automatically follows local time:

- `06:00` through `16:59`: daytime MP4 background;
- `17:00` through `05:59`: nighttime MP4 background;
- video backgrounds loop silently and use cover scaling without changing aspect ratio.

The original purchased model files are immutable local backup assets. The
project owner has confirmed that the Xiaohudie and Felix runtime copies may be
tracked in this repository for development and testing; this exception does not
authorize redistribution through other repositories or standalone asset
packages.

The selectable Felix runtime must include:

- all 22 supplied expression presets registered in `model3.json`;
- `ParamMouthOpenY` in the `LipSync` parameter group;
- an isolated `felix_001` character configuration and persona;
- the local `zh_CN-chaowen-medium` Piper voice, isolated from Xiaohudie's `zh_CN-huayan-medium` voice;
- no automatic use of outfit, prop, or pose presets as conversational emotions.

Switching to Felix changes the Live2D model, persona, and TTS voice together. Switching back restores the Xiaohudie model, persona, and voice. Xiaohudie remains the startup default.

---

## 9. Canonical modality model

### Text modality

Input:

- ASR transcript only.

Must not receive:

- raw audio;
- video;
- audio emotion;
- video emotion;
- conflict result.

Output:

- normalized valence label;
- optional fine emotion;
- confidence;
- evidence;
- quality estimate based on available ASR/text metadata.

### Audio modality

Input:

- raw user-turn audio only;
- an instruction to ignore lexical meaning.

Must not receive:

- transcript;
- video;
- text emotion;
- conflict result.

Output:

- normalized valence label;
- optional fine emotion;
- confidence;
- evidence based on vocal/prosodic characteristics;
- local audio quality.

### Video modality

Input:

- user-turn video or sampled frames only;
- no audio track where practical;
- an instruction to ignore subtitles and semantic text.

Must not receive:

- transcript;
- raw audio;
- audio emotion;
- text emotion;
- conflict result.

Output:

- normalized valence label;
- optional fine emotion;
- confidence;
- visible evidence;
- standardized observed actions from the ordered frame sequence;
- face/video quality.

Observed actions remain part of the video modality. They must not be counted as
an additional independent modality. A deterministic, bounded mapping may use a
high-confidence action as weak video-emotion evidence; semantic actions such as
head shaking must not be treated as proof of a negative internal state.

---

## 10. Canonical label space

MVP labels:

```text
positive
neutral
negative
uncertain
```

Provider-specific labels must be normalized at the provider boundary.

Fine-grained labels may be preserved as non-authoritative metadata.

The fusion layer operates only on canonical labels and reliability values.

---

## 11. Reliability and evidence rules

Canonical reliability:

```text
reliability = confidence × quality
```

For the final emotion summary, deterministic fusion computes a normalized
reliability-weighted sum:

```text
weighted_score = Σ(label_score × modality_weight × reliability)
                 / Σ(modality_weight × reliability)
```

where positive is `+1`, neutral is `0`, and negative is `-1`. Uncertain or
unreliable observations do not contribute. Fewer than two reliable modalities
must produce `insufficient_evidence`, not a strong final label.

This is an engineering heuristic, not a calibrated psychological probability.

Default reliable-modality threshold:

```text
0.55
```

The threshold must be configurable.

Strong conflict must not be emitted unless at least two relevant modalities are reliable.

`uncertain` and `insufficient_evidence` are valid and expected outcomes.

---

## 12. Canonical conflict types

Required MVP conflict results:

```text
consistent_positive
consistent_neutral
consistent_negative
verbal_positive_behavior_negative
verbal_negative_behavior_positive
audio_visual_disagreement
uncertain
insufficient_evidence
```

Interpretation:

- `behavior` means reliable nonverbal audio and/or visual signals;
- conflict is an interaction cue, not proof of concealment or deception.

The system must not label the user as deceptive.

---

## 13. Canonical companion strategies

Required MVP strategies:

```text
positive_engagement
emotional_validation
gentle_check_in
calm_listening
neutral_clarification
normal_conversation
```

Minimum mapping:

```text
consistent_positive
-> positive_engagement

consistent_negative
-> emotional_validation

verbal_positive_behavior_negative
-> gentle_check_in

audio_visual_disagreement
-> neutral_clarification

uncertain / insufficient_evidence
-> normal_conversation
```

The response model may phrase the response freely within safety constraints, but it may not override the authoritative strategy without explicit code support.

---

## 14. Safety behavior

The system must:

- frame emotion output as uncertain observation;
- use nonjudgmental language;
- avoid diagnosis;
- avoid claims of mind-reading;
- avoid coercion;
- permit the user to decline;
- avoid escalating ordinary negative affect into crisis language;
- avoid presenting model confidence as scientific certainty.

Example acceptable style:

```text
“听起来你可能有些疲惫。今天是不是消耗比较大？不想展开说也没关系。”
```

Example forbidden style:

```text
“你明明很难过，只是不愿承认。”
```

---

## 15. Privacy and data handling

### Default

- camera processing is opt-in;
- raw audio/video is temporary;
- temporary files are deleted after inference;
- conversation and media are not retained by default;
- logs store metadata, not raw media;
- provider uploads are limited to the current turn;
- user-facing settings must allow disabling video analysis.

### Debug mode

Debug retention may be enabled only through explicit configuration.

When enabled:

- the UI must indicate that media retention is active;
- retained files must be written to a user-visible application data directory;
- cleanup controls must be available;
- secrets must never be stored alongside retained media.

### Provider disclosure

The application must clearly state that configured cloud providers may receive the current turn's media or transcript.

---

## 16. Availability and fallback

The application must continue normal conversation under partial failure.

Required fallbacks:

```text
camera disabled
-> text + audio

no valid face
-> text + audio

audio emotion timeout
-> text + video

video emotion timeout
-> text + audio

all emotion providers unavailable
-> ordinary text conversation

TTS failure
-> show text reply

avatar failure
-> preserve text/voice conversation when practical
```

Emotion inference must have a latency budget and must not block indefinitely.

---

## 17. Packaging contract

The end user must not need to install:

- Python;
- Node.js;
- uv;
- FFmpeg;
- Git.

The packaged app must include or provision all required runtime components.

The desktop app must:

- launch the local backend automatically;
- wait for backend health;
- display startup errors;
- terminate child processes on exit;
- store user settings in the OS application-data location;
- keep API keys out of the renderer process;
- listen only on loopback for local backend communication.

---

## 18. MVP functional acceptance criteria

The Windows MVP is accepted when:

1. the app launches from a desktop build;
2. the Live2D avatar loads;
3. microphone speech produces ASR text;
4. the app generates and speaks a reply;
5. lip sync works through `ParamMouthOpenY`;
6. the camera can be enabled and disabled;
7. one user turn yields aligned audio and video artifacts internally;
8. text, audio, and video emotion providers return canonical schemas;
9. ordered video frames can report a standardized action such as `wave` without
   creating a fourth modality;
10. low-quality video does not cause strong conflict;
11. a verbal-positive / behavioral-negative test triggers `gentle_check_in`;
12. provider failure degrades to ordinary conversation;
13. temporary media is removed by default;
14. secrets are not present in the repository or renderer;
15. the app exits without leaving backend processes running.

---

## 19. Evaluation plan

Minimum comparison matrix:

```text
A. text-only conversation
B. text + naive multimodal final label
C. independent modalities + reliability-aware conflict detection
```

Provider comparison:

```text
MiMo-V2.5
vs.
Qwen3-Omni-Flash
```

Minimum metrics:

- modality emotion classification agreement with manual annotation;
- conflict detection precision/recall or accuracy;
- false strong-conflict rate;
- insufficient-evidence accuracy;
- JSON/schema success rate;
- mean and P95 latency;
- per-turn API cost;
- response-strategy appropriateness;
- user-rated feeling of being understood.

Provider-generated confidence must not be reported as calibrated accuracy.

---

## 20. Explicitly out of scope for MVP

- continuous full-duplex multimodal streaming;
- training a new multimodal foundation model;
- fine-tuning MiMo, Qwen, or GLM;
- persistent psychological profiles;
- long-term personal memory;
- emotion-based medical advice;
- deception detection;
- hidden background camera recording;
- multi-user face tracking;
- mobile apps;
- Linux desktop packaging;
- automatic cloud account provisioning;
- autonomous emergency escalation;
- arbitrary Live2D motion generation;
- redistribution of purchased avatar assets outside the owner-approved repository and runtime use.

These may be considered only after the MVP is accepted.
