# Action, text emotion, and deterministic fusion

## Runtime contract

One turn produces independent canonical observations:

```text
ASR transcript only          -> GLM text emotion
ordered silent video frames -> MiMo visual emotion + observed actions
raw audio only              -> MiMo audio emotion
```

The text provider never receives images, actions, audio, or another modality's
result. The video provider never receives the transcript or audio result. The
audio provider receives raw turn audio plus the audio-only prompt, never the
transcript or visual observation.

## Action recognition

MiMo receives up to the configured number of ordered frames and may return:

```text
wave
thumbs_up
clap
nod
head_shake
hands_up
point
still
other
```

Temporal actions such as `wave`, `clap`, `nod`, and `head_shake` require evidence
across frames. A single hand-up frame is not sufficient evidence for `wave`.

An action is nested inside the video `ModalityEmotion`; it is not a fourth
modality. This prevents camera evidence from being counted twice.

## Action-to-emotion mapping

The provider observes actions. Deterministic Python code applies a conservative
prior only when action confidence is at least `0.60`:

| Action | Valence prior | Prior strength |
| --- | --- | --- |
| `wave` | positive | 0.45 |
| `thumbs_up` | positive | 0.80 |
| `clap` | positive | 0.70 |
| `nod` | neutral | 0.35 |
| `head_shake` | neutral | 0.35 |

Other actions are retained as observations but have no emotion prior. In
particular, head shaking is not treated as proof of negative emotion. Action
evidence can contribute at most `0.25` of the video-emotion calculation. These
thresholds are configured in `configs/app.example.yaml`.

## Final weighted emotion

Only `status=ok`, non-uncertain observations whose reliability reaches `0.55`
participate. Canonical label scores are:

```text
positive = +1
neutral  =  0
negative = -1
```

The normalized weighted sum is:

```text
weighted_score = Σ(label_score × modality_weight × reliability)
                 / Σ(modality_weight × reliability)
```

Default weights:

```text
text  = 0.45
audio = 0.25
video = 0.30
```

When audio is absent, the text/video contributions are naturally renormalized.
Scores at least `0.25` are positive; scores at most `-0.25` are negative; values
between them are neutral. Fewer than two reliable modalities produces
`uncertain` with `insufficient_evidence`.

Conflict classification and companion strategy are computed separately from the
weighted label. For example, reliable positive text plus reliable negative video
still yields `verbal_positive_behavior_negative -> gentle_check_in`, even if the
configured weights make the final weighted label positive.

## Current integration status

Implemented and offline-tested:

- MiMo action parsing and normalization;
- bounded action-to-video-emotion mapping;
- GLM text-only emotion provider and timeout fallback;
- MiMo raw-audio emotion provider, local WAV quality and timeout fallback;
- deterministic fusion and conflict classification;
- parallel text/audio/video middleware;
- per-modality expression suggestions and deterministic final AvatarState;
- paid opt-in debug command;
- camera preview中的按轮次云端分析、逐阶段状态和 metadata-only 调试目录。

The pinned Open-LLM-VTuber process currently runs in its own Python 3.10 runtime,
while the canonical backend targets Python 3.11. The live conversation path does
not yet call this middleware automatically. The debug screen now validates the
complete camera-to-fusion path with optional manual transcript; automatic ASR turn
alignment still requires the loopback backend API and a narrow Open-LLM-VTuber
adapter at the post-ASR/pre-agent insertion point.
