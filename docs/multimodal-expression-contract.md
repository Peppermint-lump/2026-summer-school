# 三模态情绪与角色表情共同接口

状态：MVP `1.0`，依据 `SSOT.md` 与 `ARCHITECTURE.md`。

## 1. 不可跨越的输入边界

```text
ASR transcript only -> GLM text emotion  -> ModalityEmotion(text)
raw turn audio only -> MiMo audio emotion -> ModalityEmotion(audio)
ordered frames only -> MiMo video emotion -> ModalityEmotion(video)
```

- GLM 不接收原始音频、图片、视频或其他模态结果。
- MiMo audio 请求不接收 transcript、图片或视频；prompt 禁止依赖词义。
- MiMo video 请求不接收 transcript 或音频；动作属于 video 内部证据。
- 三个 Provider 请求彼此独立，可并行执行，任何一个失败都必须 fail-open。

## 2. 单模态响应

每个实际存在的输入都返回一个 `ModalityEmotion`。缺失、关闭、低质量、
超时和 Provider 错误也返回规范对象，不抛出导致整轮失败的异常。

每个观察再由确定性 `AvatarStateMapper` 产生一个
`ModalityExpression`：

```json
{
  "schema_version": "1.0",
  "modality": "audio",
  "source_label": "positive",
  "avatar_emotion": "affection",
  "expression": "heart",
  "reliability": 0.72,
  "contributes_to_fusion": true
}
```

这只是该输入自己的建议，不是最终角色表情。

## 3. 加权与最终表情

只有 `status=ok`、非 `uncertain` 且 reliability 达到阈值的观察参与融合：

```text
weighted_score = Σ(label_score × modality_weight × reliability)
                 / Σ(modality_weight × reliability)
```

默认权重：text `0.45`、audio `0.25`、video `0.30`。

少于两个可靠模态时：

- 保留每个已有输入自己的 `ModalityExpression`；
- `ConflictResult` 为 `insufficient_evidence`；
- 若恰好一个输入可靠，角色可以采用该输入自己的保守表情建议，但
  `AvatarState.source_label` 仍为 `uncertain`，不能伪造强跨模态结论；
- 没有可靠输入时最终 `AvatarState` 使用 neutral。

至少两个可靠模态时，由确定性代码输出最终 label、冲突、策略和
`AvatarState`。通用 negative 不自动触发 cry；只有高可靠且明确出现哭泣/
流泪证据时才允许 cry。可靠 wave 可以选择 `greeting` motion，但 wave 仍然
只计入 video 一次。

## 4. 权威返回对象

`EmotionMiddleware.analyze_turn(TurnRecord)` 返回：

```text
EmotionTurnResult
├── analysis: EmotionTurnAnalysis
│   ├── observations: text, audio, video
│   └── fusion: ConflictResult
└── avatar_state: AvatarState
    ├── modality_expressions
    ├── final emotion/expression
    └── optional motion
```

Provider 原始响应、base64、媒体路径和 API key 不得进入该返回对象。

## 5. Live2D 运行接入

`AvatarState.expression` 是角色表情的权威输入，GLM 回复中的自由表情标签
不能覆盖它。Open-LLM-VTuber 在 ASR 完成后通过带临时 token 的 loopback
接口调用中间件，把最终 expression 转为前端 actions，并把 `wave` 对应的
`greeting` motion 发给动作控制器。陪伴 GLM 只接收规范观察摘要与策略，
不接收原始媒体。

每轮元数据调试输出位于：

```text
runtime/debug/emotion_turns/<turn_id>/
├── 00_request.json
├── 01_text_observation.json
├── 02_audio_observation.json
├── 03_video_observation.json
├── 04_fusion.json
├── 05_avatar_state.json
├── 06_cleanup.json
└── summary.json
```

目录内不记录 transcript、WAV、视频帧、base64 或 API key。整轮三路分析
结束后，`runtime/turns/<turn_id>/` 下的临时媒体由唯一编排器统一删除。
