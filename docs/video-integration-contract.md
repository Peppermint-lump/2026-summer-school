# 视频侧集成契约

状态：团队共同接口，MVP `1.0`。
依据：`SSOT.md`、`ARCHITECTURE.md`。当本文与二者冲突时，以二者为准。

## 1. 边界与所有权

LZY 视频侧负责：

```text
摄像头 -> 时间戳帧缓存 -> turn 对齐帧 -> 本地视频质量
       -> video-only Provider -> ModalityEmotion(video)
```

ZZH 集成侧负责：

```text
VAD/ASR -> speech_start_ms / speech_end_ms -> TurnRecord
ModalityEmotion(text/audio/video) -> fusion -> companion -> avatar
```

共同接口只传递规范化对象，不传递 Provider SDK 类型。视频模块不得接收转写文本、
原始音频、文本/音频情绪或冲突结果；回复模型不得接收原始视频。

## 2. 时间约定

- 所有 `*_ms` 都是 Unix epoch 毫秒整数。
- `speech_start_ms` 与 `speech_end_ms` 为闭区间。
- `speech_end_ms >= speech_start_ms`。
- 摄像头帧必须在采集时立即附加同一时钟来源的时间戳。
- 说话轮次只能请求当前 `turn_id` 的时间范围，视频侧不得跨 turn 混用帧。
- 独立视觉观察使用 `visual_<unix_ms>` 标识和最近 3 秒的有序帧窗口，绝不附带
  transcript 或 audio。

## 3. `TurnRecord` 1.0

必填字段：

| 字段 | 类型 | 所有者 | 说明 |
|---|---|---|---|
| `schema_version` | `"1.0"` | shared | 固定版本 |
| `session_id` | 非空字符串 | integration | 当前会话标识 |
| `turn_id` | 非空字符串 | integration | 当前发言轮次标识 |
| `speech_start_ms` | 整数 | integration | 用户发言开始 |
| `speech_end_ms` | 整数 | integration | 用户发言结束 |

媒体路径与 `transcript` 可为空。路径只在进程内部传递，不进入日志和用户回复。

## 4. 视频侧输入与产物

视频侧接收 `TurnRecord`，返回 `VideoTurnArtifact`：

```json
{
  "schema_version": "1.0",
  "turn_id": "turn_000001",
  "status": "ok",
  "frame_paths": ["runtime/turns/turn_000001/video/frame_000001.jpg"],
  "video_path": null,
  "captured_frame_count": 42,
  "sampled_frame_count": 8,
  "quality": 0.81,
  "quality_reasons": []
}
```

`status` 只能是：`ok`、`insufficient_evidence`、`disabled`、`capture_error`。
摄像头关闭、无人脸或质量不足是正常降级结果，不得抛出导致整轮对话失败的异常。

## 5. `ModalityEmotion` 1.0

视频侧对外只返回 `modality = "video"` 的规范对象：

```json
{
  "schema_version": "1.0",
  "modality": "video",
  "label": "negative",
  "fine_emotion": "subdued",
  "confidence": 0.74,
  "quality": 0.81,
  "reliability": 0.5994,
  "evidence": ["可见表情变化较少"],
  "status": "ok",
  "raw_metadata": {"provider": "mimo", "prompt_version": "video_emotion_v1"}
}
```

约束：

- `label`：`positive`、`neutral`、`negative`、`uncertain`；
- `status`：`ok`、`uncertain`、`insufficient_evidence`、`provider_error`、
  `timeout`、`disabled`；
- `confidence`、`quality`、`reliability` 范围均为 `[0, 1]`；
- `reliability = confidence * quality`，由确定性代码计算；
- Provider 证据必须只描述画面可见信息；
- `raw_metadata` 不得包含帧、base64、路径、密钥或完整 Provider 响应。

## 6. 生命周期与清理

1. 用户明确开启摄像头后才启动采集。
2. 集成侧在 speech end 后使用 `TurnRecord` 请求视频产物。
3. 视频侧完成质量评估；证据不足时不调用 Provider。
4. Provider 成功、失败、超时或任务取消后，均进入清理阶段。
5. 默认删除当前 turn 的帧和视频；只有显式 debug-retention 配置可以保留。

### 6.1 自动视觉观察

- 正式启动器在摄像头与视频分析均启用时启动唯一后台观察器；
- 默认每 2 秒分析最近 3 秒窗口；摄像头以 10 FPS 缓存并均匀抽取约
  5 FPS/15 张有序帧，不要求文本、语音或手动按钮；
- 最新结果通过已鉴权的 `GET /v1/visual/latest` 暴露给上游适配器；
- Open-LLM-VTuber 每 0.5 秒检查序号，只推送新结果；
- `wave` 映射为 `greeting`，相同问候动作默认 5 秒内不重复执行；
- 置信度不低于 `0.60`、暂时没有专属 Live2D 动作的非静止动作（`thumbs_up`、
  `clap`、`nod`、`head_shake`、`hands_up`、`point`、`other`）映射为语义中性的
  `observe`：角色随机先看左或右，再看向另一侧并回到 `Idle`；
- `still` 和低置信动作均保持 `idle`；`wave` 优先级高于 `observe` 兜底；相同的
  连续事件采用边沿触发，必须先观察到非该事件才允许再次执行；
- 说话期间后台观察器仍工作，因此明确动作可以即时驱动 Live2D；说话结束后，
  原有按轮次三模态分析独立完成加权和最终表情；
- 视觉事件只驱动动作/表情，不触发聊天模型、TTS 或主动语言回复。

## 7. 集成验收示例

- 摄像头关闭：返回 `disabled`，系统继续 text + audio。
- 时间范围内无帧：返回 `insufficient_evidence`。
- 无有效人脸/画面过暗：低质量不得形成强冲突。
- Provider 超时：返回 `timeout`，普通对话继续。
- 正常视频：返回合法 `ModalityEmotion(video)`，不携带 transcript。
- 高置信非静止动作（无专属动作）：返回 `AvatarState.motion=observe`，前端完成左右观察、参数恢复
  和 `Idle` 重启，不触发文本回复或 TTS。
- 清理关闭 retention：当前 turn 媒体在成功和失败后均被删除。
