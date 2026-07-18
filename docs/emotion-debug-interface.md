# 情绪与动作链路调试接口

本文档固定本地调试页面、按轮次分析接口和调试文件契约。它只用于开发验证，
不代替桌面应用的正式 loopback API。

Open-LLM-VTuber 左下角的“直播”是浏览器本地摄像头预览，只用于确认取景，
不是正式 MiMo 输入，也不触发分析。正式视觉输入由后端 `CameraBuffer` 提供；
即使不打开“直播”，只要正式启动配置已启用摄像头，连续视觉分析仍会运行。
访问 VTuber 页面时加 `?visualDebug=1` 可显示可靠度、轮次和轨迹目录；普通模式
只显示简洁的最新动作/情绪状态。

## 1. 当前链路

```text
正在运行的 CameraBuffer
-> 未来 1-15 秒有序帧
-> 本地人脸/亮度/清晰度质量评估
-> 2 FPS、最多 12 帧的临时 JPEG
-> MiMo 视频情绪与标准动作观察
-> 可选 GLM 文字情绪（手动输入代替尚未接入的 ASR）
-> 确定性 reliability 加权与冲突策略
-> 页面结果 + 每轮 metadata-only JSON
-> 删除临时 JPEG
```

声音模态当前明确返回 `not_implemented`，不参与融合。动作属于视频模态内部证据，
不会作为第四模态重复加权。

## 2. 本地 HTTP 契约

服务只监听 `127.0.0.1`，每次启动生成临时 token。所有接口必须携带
`?token=<ephemeral-token>`。

### `GET /api/status`

返回实时摄像头质量，以及：

```json
{
  "analysis_available": true,
  "analysis_state": "idle",
  "analysis_result": null,
  "analysis_error": null
}
```

`analysis_state` 取值：

```text
idle -> queued -> capturing -> preprocessing -> provider_analysis
     -> fusion -> completed
```

失败状态为 `failed`。单个 Provider 的预期超时或错误由模态服务转换成 canonical
fallback，仍会进入融合并完成本轮，不会使摄像头服务退出。

Provider 延迟预算可分别用 `VIDEO_EMOTION_TIMEOUT_SECONDS` 和
`TEXT_EMOTION_TIMEOUT_SECONDS` 配置。`evidence` 会用非敏感错误码区分
`provider_timeout`、`provider_rate_limited`、`provider_invalid_output` 和
`provider_request_failed`，不会写 Provider 原始响应或鉴权信息。

### `POST /api/analyze`

请求：

```json
{
  "duration_seconds": 5,
  "transcript": "我今天很开心"
}
```

- `duration_seconds` 必须在 1 到 15 之间；
- `transcript` 可为 `null`，最长 4000 字符；
- 一个时刻只允许一个分析轮次；
- `202` 表示已接受，`409` 表示已有轮次运行，`503` 表示 Provider 未配置；
- API Key 只存在于 Python 进程，不返回浏览器。

### `POST /api/shutdown`

停止本地预览服务器，启动脚本随后在 `finally` 中关闭摄像头。

## 3. 调试文件契约

默认输出根目录：

```text
runtime/debug/emotion_pipeline/
```

每轮创建 `debug_<unix_ms>/`，包含：

| 文件 | 内容 |
| --- | --- |
| `00_request.json` | turn ID、采集时长、启用输入，不保存完整 transcript |
| `01_capture_quality.json` | 帧数、人脸、多人、亮度、清晰度、质量原因 |
| `02_frame_sampling.json` | 捕获/采样/上传帧数量，不保存帧路径 |
| `03_video_observation.json` | 视频 label、fine emotion、可靠性、`wave` 等动作 |
| `04_text_observation.json` | 独立文字 label，或 disabled/insufficient 状态 |
| `05_fusion.json` | weighted score、最终 label、冲突、策略 |
| `06_cleanup.json` | 临时媒体是否完成清理 |
| `summary.json` | 页面展示的完整汇总 |

目录不会包含图片、视频、音频、base64、Authorization 或 API Key。若
`06_cleanup.json` 的 `raw_media_may_remain` 为 `true`，应视为异常并检查
`runtime/turns/<turn_id>/`。

可以用参数改变 metadata 输出位置：

```bash
.venv/bin/python scripts/start_camera_preview.py \
  --debug-output runtime/debug/my_run
```

## 4. 结果解释

- `confidence` 是 Provider 自报置信度，不是校准后的准确率；
- `quality` 来自本地输入质量；
- `reliability = confidence × quality`；
- 只有 `status=ok` 且 reliability 达到 `0.55` 的模态参与最终融合；
- 当前只有视频时，最终融合必须为 `insufficient_evidence`；填写文字并且文字、
  视频都可靠时，才产生双模态加权结果；
- `wave` 可以作为最多 25% 的弱视频情绪证据，但不等于用户真实内心状态。
