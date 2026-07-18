# 视频模块本地配置与调试

## 1. 本地配置

复制示例配置并仅在本机修改：

```bash
cp configs/app.example.yaml configs/app.local.yaml
```

`configs/app.local.yaml` 已被 Git 忽略。默认调试配置应满足：

```yaml
capture:
  camera:
    enabled: true
    retain_media: false

emotion:
  video:
    enabled: false
```

这允许本地摄像头质量测试，但不会上传画面或产生 API 费用。

## 2. 摄像头 smoke test

```bash
.venv/bin/python scripts/debug_video_pipeline.py --mode camera --duration 5
```

macOS 首次运行时需要在系统摄像头权限窗口中明确允许当前终端/Codex。
脚本只输出帧数、亮度、清晰度、人脸有效比例和质量原因；摄像头会在
`finally` 中关闭，camera 模式不会将帧写入磁盘。

## 3. 实时调试屏幕

```bash
.venv/bin/python scripts/start_camera_preview.py
```

命令会打印一个带临时访问令牌的 `http://127.0.0.1:8765/` 地址。在浏览器中
打开后可以看到实时画面、视频管线收帧状态、人脸帧数、多人帧、质量和降级原因。
点击页面中的“停止摄像头和服务器”可以安全退出。

该页面只验证摄像头和人脸质量链路，不调用付费 Provider，因此实时状态显示
“按轮次 Provider 分析”。按 turn 的动作识别由 MiMo 有序多帧分析实现，结果在
下方 Provider smoke test 完成后输出；实时本地动作叠加层仍是后续工作。

## 4. MiMo provider smoke test

这是一次显式、可能产生费用的当前 turn 媒体上传。先复制 `.env.example` 为
被 Git 忽略的 `.env`，填写 `MIMO_API_KEY`，确认 `MIMO_BASE_URL`，并设置：

```dotenv
VIDEO_EMOTION_ENABLED=true
TEXT_EMOTION_ENABLED=true
```

模型、端点和开关会从 `.env` 覆盖本地 YAML。然后运行：

```bash
.venv/bin/python scripts/debug_video_pipeline.py --mode provider --duration 5
```

在五秒内挥手，并提供本轮 ASR 文本，可同时查看标准化动作、文本情绪和最终融合：

```bash
.venv/bin/python scripts/debug_video_pipeline.py --mode provider --duration 5 \
  --transcript "我今天感觉很好"
```

输出中的 `observed_actions` 是视频模态内部证据。动作最多占视频结果的 25%，随后
视频结果才与文本结果按 `modality_weight × reliability` 加权；动作不会作为第四个
模态被重复计算。

不要把密钥写入 YAML、命令历史、日志或 Git。Provider 模式默认在推理结束、
失败或超时后删除当前 turn 的采样帧。

## 5. 自动检查

```bash
.venv/bin/ruff format --check apps packages scripts/debug_video_pipeline.py scripts/start_camera_preview.py tests
.venv/bin/ruff check apps packages scripts/debug_video_pipeline.py scripts/start_camera_preview.py tests
.venv/bin/mypy apps packages scripts/debug_video_pipeline.py scripts/start_camera_preview.py
.venv/bin/python -m unittest discover -s tests -v
```

## 6. 待评估：MiMo 原生短视频输入

当前默认摄像头画面为 `640x480`，帧导出的最长边上限为 768，因此默认配置下
不会把画面缩小成低分辨率截图。现有 Provider 发送的是按 2 FPS 采样、最多 12 张
的 JPEG 序列，已经可以返回标准化动作；后续仍应比较该方案与 MiMo 静音短视频
输入的准确率、延迟和费用，不能把效果建立在“当前截图分辨率很低”的假设上。
