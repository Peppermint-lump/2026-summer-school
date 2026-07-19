# 当前文字、语音与图片情绪链路说明

状态：已实现，适用于 `feat/lzy-face` 分支当前版本。

本文面向项目协作者，说明用户输入进入系统后，文字、语音和图片之间究竟是什么
关系，以及它们如何共同决定回复策略、Live2D 表情和动作。规范接口细节见
[`multimodal-expression-contract.md`](multimodal-expression-contract.md)。

## 1. 一句话结论

三路输入是“独立观察、统一格式、确定性融合”，不是把文字、声音和图片一起交给
一个模型直接猜最终情绪：

```text
文字/ASR transcript ──> GLM 文字观察 ─────> ModalityEmotion(text)  ┐
原始本轮语音 ────────> MiMo 语音观察 ─────> ModalityEmotion(audio) ├─> 确定性融合
有序摄像头帧 ────────> MiMo 视频观察 ─────> ModalityEmotion(video) ┘
                                                               │
                                                               ├─> 回复策略与 GLM 回复
                                                               └─> Live2D 表情与动作
```

这里的“独立”指模型观察阶段互不偷看；“融合”指三路完成观察后，由项目代码根据
可靠度和配置权重计算共同结果。两者并不矛盾。

## 2. 三路输入分别负责什么

### 2.1 文字层：用户表达了什么

来源有两种：

- 用户在网页输入框直接输入的文字；
- 用户说话后，由 ASR 生成的 transcript。

文字情绪 Provider 是 GLM。这个请求只接收本轮文字，不接收音频、摄像头帧或
MiMo 的结论。它输出文字自己的：

- 标准情绪：`positive / neutral / negative / uncertain`；
- 细粒度描述；
- confidence、quality 和 reliability；
- status 与文字证据。

注意：文字情绪 GLM 和最终生成角色台词的陪伴 GLM 是两个逻辑职责。前者只产生
`ModalityEmotion(text)`，后者只能在融合完成后，根据规范摘要和策略组织回复。
最终回复本身不能反过来充当文字情绪标签。

### 2.2 语音层：用户是怎样说的

语音情绪 Provider 是 MiMo。它只接收本轮原始音频，关注音高、能量、节奏、停顿
等非文字线索，不接收 ASR transcript、图片或其他模态结果。因此，即使同一句话
的字面意思积极，声音也可以独立返回中性或消极观察。

ASR 和语音情绪分析使用同一段说话产生的不同表示：

```text
同一段麦克风输入
├─> ASR ─> transcript ─> GLM 文字情绪
└─> raw audio ─────────> MiMo 语音情绪
```

如果本轮是打字、没有录到声音，audio 仍返回一个规范对象，但状态为
`insufficient_evidence`，可靠度为 0，不参与融合，也不会阻断回复。

### 2.3 图片/视频层：用户看起来在做什么

摄像头并不是只截取一张任意图片。后端持续维护带时间戳的帧缓冲区，每次分析从
一个有序时间窗口中采样多帧，交给 MiMo 视频 Provider。MiMo 只接收这些帧，不接收
文字、音频或其他情绪结论，因此可以独立观察：

- 面部和姿态呈现出的弱情绪线索；
- `wave`、`thumbs_up`、`clap`、`nod`、`head_shake`、`hands_up`、
  `point`、`still` 或 `other` 等连续动作；
- 画面质量和动作证据。

动作不是第四个模态。动作是 `ModalityEmotion(video)` 内部的
`observed_actions`，可按受限规则作为视频情绪的弱证据，但进入总融合时 video
仍然只计算一次。例如 `thumbs_up` 可以帮助视频层判断积极倾向，也可以触发
Live2D 的 `observe` 兜底动作，但不能额外增加一份“动作模态”权重。

## 3. 输入发生时，三路怎样对齐

### 3.1 用户说话

一次语音 turn 会形成真实的 `speech_start_ms / speech_end_ms`：

1. 原始音频交给 ASR，得到 transcript；
2. transcript 交给 GLM 文字情绪；
3. 原始音频独立交给 MiMo 语音情绪；
4. 摄像头缓冲区选取同一说话时间范围内的有序帧，交给 MiMo 视频情绪；
5. 三个规范观察汇合。

因此用户一边说话一边做动作时，文字、语气和同期动作属于同一个 `turn_id`，但
模型分析仍然彼此独立。

### 3.2 用户打字

打字没有真实语音时长，所以系统不会伪造一段 speech：

- `speech_start_ms == speech_end_ms`，如实表示本轮没有说话；
- 另外提供 `visual_start_ms / visual_end_ms`；
- 默认视觉窗口为提交文字前最近 3 秒。

这样 GLM 分析本轮文字，MiMo 分析提交前的连续摄像头帧，两路使用同一个
`turn_id`，最后参与同一轮融合。音频层因缺失而退出融合。

### 3.3 用户只做动作、不说话也不打字

摄像头开启后，后台还有一条连续 video-only 链路：

```text
最近 3 秒有序帧 -> MiMo video -> 视频情绪/动作 -> Live2D
```

它可以让 `wave` 触发 `greeting`，或让高置信的非静止动作触发中性的 `observe`，
不需要先发一条文字，也不会自动调用对话 GLM 生成台词。

当正常文字/语音 turn 正在回复时，这条连续链路仍可发送 motion，但会设置
`expression_suppressed=true`，防止它用单独的视频表情覆盖本轮融合表情。

## 4. Emotion 如何融合

每一路先转换为相同的 `ModalityEmotion` 结构。可靠度由确定性代码计算：

```text
reliability = confidence × quality
```

当前只有满足以下条件的观察才参与总融合：

- `status == ok`；
- label 不是 `uncertain`；
- reliability 不低于配置阈值，默认 `0.55`。

默认模态权重为：

| 模态 | 默认权重 | 表示的信息 |
| --- | ---: | --- |
| text | 0.45 | 用户明确表达的文字内容 |
| audio | 0.25 | 语气、能量、节奏等非文字声音线索 |
| video | 0.30 | 表情、姿态和连续动作线索 |

label 先映射为 `positive=+1`、`neutral=0`、`negative=-1`，随后计算：

```text
weighted_score = Σ(label_score × modality_weight × reliability)
                 / Σ(modality_weight × reliability)
```

至少两个模态可靠时，融合层才会给出跨模态最终 label，并判断一致或冲突。例如：

- 三路都积极：`consistent_positive`；
- 文字积极，但可靠的语音/视频消极：
  `verbal_positive_behavior_negative`；
- 可靠语音与可靠视频方向不同：`audio_visual_disagreement`。

少于两个可靠模态时，结果必须是 `insufficient_evidence`。单个可靠模态仍可给
Live2D 一个保守的表情或动作建议，但不能冒充跨模态融合结论。

## 5. 融合之后分别影响什么

融合产生：

- 最终 emotion label 和 weighted score；
- conflict type、conflict score；
- companion strategy；
- 每个模态自己的表情建议；
- 权威 `AvatarState.expression` 和可选 motion。

之后分成两个输出方向：

1. **角色语言**：陪伴 GLM 收到规范摘要，包括三路 label/reliability/status、
   视频动作、融合 label/conflict/strategy。它不接收原始帧、base64 或原始音频，
   只能根据这些不确定观察生成克制的回复。
2. **Live2D**：`AvatarState.expression` 决定最终表情；视频中的 `wave` 等动作可
   决定 `greeting / observe / idle`。GLM 自由生成的表情标签不能覆盖权威融合表情。

所以“融合”并不表示三个 Provider 共享输入，而是它们先独立看完各自证据，再把
规范结果交给一套可测试、可解释的代码共同决策。

## 6. 常见输入组合与降级行为

| 当前输入 | 实际分析 | 融合/回应行为 |
| --- | --- | --- |
| 打字 + 摄像头 | GLM text + MiMo video；audio 缺失 | 两路可靠时进行 text/video 融合 |
| 说话 + 摄像头 | ASR/GLM text + MiMo audio + MiMo video | 三路独立观察后融合 |
| 只做动作 | MiMo video-only | 直接驱动 Live2D motion，不自动生成台词 |
| 摄像头关闭 | text + audio | video=`disabled`，正常继续对话 |
| 音频情绪失败 | text + video | audio fail-open，不中止回复 |
| 视频质量不足/超时 | text + audio | 不把低质量视觉当作可靠证据 |
| 只有一个可靠模态 | 该模态的保守建议 | 总融合为 `insufficient_evidence` |
| emotion API 全部失败 | 普通文字对话 | 不阻断陪伴回复 |

输出 TTS 属于角色回复后的声音合成，不是用户的 audio emotion 输入，两者不要混淆。

## 7. 当前代码位置

| 职责 | 当前实现 |
| --- | --- |
| 三路并行编排 | `apps/backend/app/integration/emotion_middleware.py` |
| 文字情绪 | `apps/backend/app/emotion/text/` |
| 语音情绪 | `apps/backend/app/emotion/audio/` |
| 视频情绪与动作 | `apps/backend/app/emotion/video/` |
| 帧窗口对齐 | `apps/backend/app/integration/video_emotion_middleware.py` |
| 确定性融合 | `apps/backend/app/fusion/service.py` |
| Live2D 状态映射 | `apps/backend/app/avatar/state_mapper.py` |
| Loopback 共同接口与调试输出 | `apps/backend/app/integration/loopback_server.py` |
| VTuber 上游适配 | `third_party/Open-LLM-VTuber/src/open_llm_vtuber/emotion_middleware_client.py` |

## 8. 如何查看每一步

每个对话 turn 的脱敏调试信息位于：

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

建议按文件编号检查：输入是否存在和时间窗是否正确、每一路独立看到了什么、哪些
模态通过可靠阈值、最终如何融合、角色采用了什么表情和动作。调试 JSON 不保存
transcript 正文、原始音频、视频帧、base64 或 API key；临时媒体在本轮分析后清理。

## 9. 当前已验证案例

真实网页测试 `turn_245567712bda42298e63d61db1de9666` 中：

- text：GLM 返回 `neutral`，reliability `0.90`；
- audio：本轮为打字，返回 `insufficient_evidence`，不参与融合；
- video：MiMo 返回 `neutral / 平静`，reliability `0.78`，并识别到
  `thumbs_up`，动作 confidence `0.90`；
- fusion：可靠模态为 `text + video`，结果为 `consistent_neutral`；
- avatar：expression=`neutral`，motion=`observe`；
- 角色回复明确提到捕捉到竖大拇指，没有再错误声称“没有视觉”。

该案例说明目前实现同时满足“模态独立”和“emotion 必须融合”两项要求。
