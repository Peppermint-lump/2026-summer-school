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

该页面只验证当前已实现的摄像头和人脸质量链路；在手势模块完成前会明确显示
“动作识别：尚未实现”，不会伪造挥手等动作结果。

## 4. MiMo provider smoke test

这是一次显式、可能产生费用的当前 turn 媒体上传。先在本地配置中填写从
MiMo 控制台获得的 HTTPS Base URL，并设置：

```yaml
emotion:
  video:
    enabled: true
```

密钥只通过环境变量提供：

```bash
export MIMO_API_KEY='your-local-key'
.venv/bin/python scripts/debug_video_pipeline.py --mode provider --duration 5
```

不要把密钥写入 YAML、命令历史、日志或 Git。Provider 模式默认在推理结束、
失败或超时后删除当前 turn 的采样帧。

## 5. 自动检查

```bash
.venv/bin/ruff format --check apps packages scripts/debug_video_pipeline.py scripts/start_camera_preview.py tests
.venv/bin/ruff check apps packages scripts/debug_video_pipeline.py scripts/start_camera_preview.py tests
.venv/bin/mypy apps packages scripts/debug_video_pipeline.py scripts/start_camera_preview.py
.venv/bin/python -m unittest discover -s tests -v
```

## 6. 待评估：MiMo 动作视频输入

当前默认摄像头画面为 `640x480`，帧导出的最长边上限为 768，因此默认配置下
不会把画面缩小成低分辨率截图。现有 Provider 发送的是按 2 FPS 采样、最多 12 张
的 JPEG 序列；后续评估挥手等时序动作时，应比较该方案与 MiMo 静音短视频输入，
不能把成本或识别效果建立在“当前截图分辨率很低”的假设上。
