# ruff: noqa: E501
"""Loopback-only MJPEG preview for validating the current camera pipeline."""

from __future__ import annotations

import json
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import cv2

from apps.backend.app.capture.camera_buffer import CameraBuffer, CameraState
from apps.backend.app.emotion.video.face_quality import FaceQualityEvaluator


class CameraPreviewApplication:
    def __init__(
        self,
        camera: CameraBuffer,
        evaluator: FaceQualityEvaluator,
        *,
        status_window_seconds: float = 3.0,
    ) -> None:
        if status_window_seconds <= 0:
            raise ValueError("status_window_seconds must be positive")
        self.camera = camera
        self.evaluator = evaluator
        self.status_window_seconds = status_window_seconds
        self.shutdown_event = threading.Event()

    def status(self) -> dict[str, Any]:
        now_ms = time.time_ns() // 1_000_000
        frames = self.camera.frames_between(
            now_ms - int(self.status_window_seconds * 1000), now_ms
        )
        report = self.evaluator.evaluate(frames)
        pipeline_receiving = bool(frames) and self.camera.state is CameraState.RUNNING
        return {
            "camera_state": self.camera.state.value,
            "pipeline_receiving_frames": pipeline_receiving,
            "recent_frame_count": report.total_frames,
            "valid_face_frames": report.valid_face_frames,
            "multiple_face_frames": report.multiple_face_frames,
            "quality": report.quality,
            "mean_brightness": report.mean_brightness,
            "mean_sharpness": report.mean_sharpness,
            "reasons": report.reasons,
            "gesture_recognition": "provider_turn_level",
            "observed_action": None,
            "retained_media": False,
        }

    def latest_jpeg(self) -> bytes | None:
        latest = self.camera.latest_frame()
        if latest is None:
            return None
        ok, encoded = cv2.imencode(
            ".jpg",
            latest.frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 82],
        )
        if not ok:
            return None
        return cast(bytes, encoded.tobytes())


class PreviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        application: CameraPreviewApplication,
        token: str,
    ) -> None:
        super().__init__(server_address, CameraPreviewHandler)
        self.application = application
        self.token = token


class CameraPreviewHandler(BaseHTTPRequestHandler):
    server: PreviewHTTPServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlsplit(self.path)
        if not self._authorized(parsed.query):
            self._send_json({"status": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        if parsed.path == "/":
            self._send_html(_preview_html(self.server.token))
        elif parsed.path == "/api/status":
            self._send_json(self.server.application.status())
        elif parsed.path == "/stream.mjpg":
            self._stream_mjpeg()
        else:
            self._send_json({"status": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlsplit(self.path)
        if not self._authorized(parsed.query):
            self._send_json({"status": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return
        if parsed.path != "/api/shutdown":
            self._send_json({"status": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        self._send_json({"status": "stopping"})
        self.server.application.shutdown_event.set()
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def log_message(self, _format: str, *args: object) -> None:
        return

    def _authorized(self, query: str) -> bool:
        supplied = parse_qs(query).get("token", [""])[0]
        return secrets.compare_digest(supplied, self.server.token)

    def _send_html(self, html: str) -> None:
        payload = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self._security_headers("text/html; charset=utf-8", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(
        self,
        data: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._security_headers("application/json; charset=utf-8", len(payload))
        self.end_headers()
        self.wfile.write(payload)

    def _security_headers(self, content_type: str, length: int | None = None) -> None:
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; img-src 'self'; script-src 'unsafe-inline'; "
            "style-src 'unsafe-inline'; connect-src 'self'",
        )

    def _stream_mjpeg(self) -> None:
        self.send_response(HTTPStatus.OK)
        self._security_headers("multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while not self.server.application.shutdown_event.is_set():
                jpeg = self.server.application.latest_jpeg()
                if jpeg is None:
                    time.sleep(0.05)
                    continue
                self.wfile.write(b"--frame\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode())
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
                time.sleep(0.08)
        except (BrokenPipeError, ConnectionResetError):
            return


def run_camera_preview(
    application: CameraPreviewApplication,
    *,
    port: int,
) -> str:
    if not 0 <= port <= 65535:
        raise ValueError("port must be between 0 and 65535")
    token = secrets.token_urlsafe(24)
    server = PreviewHTTPServer(("127.0.0.1", port), application, token)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/?token={token}"
    print(json.dumps({"preview_url": url, "retained_media": False}), flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        application.shutdown_event.set()
        server.server_close()
    return url


def _preview_html(token: str) -> str:
    safe_token = json.dumps(token)
    return f"""<!doctype html>
<html lang="zh-CN"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>视频管线调试屏幕</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; background: #10131a; color: #eef2ff; }}
    main {{ max-width: 1180px; margin: auto; padding: 24px; }}
    h1 {{ margin: 0 0 6px; font-size: 26px; }}
    .note {{ color: #aab4ca; margin-bottom: 18px; }}
    .layout {{ display: grid; grid-template-columns: minmax(0,2fr) minmax(280px,1fr); gap: 18px; }}
    .card {{ background: #181d28; border: 1px solid #2b3446; border-radius: 14px; padding: 16px; }}
    img {{ width: 100%; aspect-ratio: 4/3; object-fit: cover; background: #050609; border-radius: 10px; transform: scaleX(-1); }}
    .status {{ display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid #2b3446; }}
    .status:last-child {{ border: 0; }} .value {{ text-align: right; }}
    .ok {{ color: #65e6a4; }} .warn {{ color: #ffc76a; }}
    button {{ margin-top: 16px; width: 100%; padding: 11px; border: 0; border-radius: 9px; background: #d95367; color: white; cursor: pointer; }}
    @media (max-width:760px) {{ .layout {{ grid-template-columns: 1fr; }} }}
  </style>
</head><body><main>
  <h1>视频管线调试屏幕</h1>
  <div class="note">仅监听 127.0.0.1；画面不写盘、不上传。当前验证摄像头与人脸质量链路。</div>
  <div class="layout"><section class="card"><img id="preview" alt="实时摄像头预览"></section>
  <aside class="card">
    <div class="status"><span>视频管线</span><strong id="pipeline" class="warn">等待帧</strong></div>
    <div class="status"><span>摄像头</span><span id="camera" class="value">—</span></div>
    <div class="status"><span>近 3 秒帧数</span><span id="frames" class="value">0</span></div>
    <div class="status"><span>有效人脸帧</span><span id="faces" class="value">0</span></div>
    <div class="status"><span>多人帧</span><span id="multiple" class="value">0</span></div>
    <div class="status"><span>画面质量</span><span id="quality" class="value">0</span></div>
    <div class="status"><span>质量原因</span><span id="reasons" class="value">—</span></div>
    <div class="status"><span>动作识别</span><strong class="warn">按轮次 Provider 分析</strong></div>
    <div class="status"><span>当前预览动作</span><span class="value">不在本地实时推理</span></div>
    <button id="stop">停止摄像头和服务器</button>
  </aside></div>
  <script>
    const token = {safe_token}; const q = `?token=${{encodeURIComponent(token)}}`;
    document.getElementById('preview').src = '/stream.mjpg' + q;
    async function refresh() {{
      const s = await (await fetch('/api/status' + q, {{cache:'no-store'}})).json();
      const pipeline = document.getElementById('pipeline');
      pipeline.textContent = s.pipeline_receiving_frames ? '正在接收帧' : '等待帧';
      pipeline.className = s.pipeline_receiving_frames ? 'ok' : 'warn';
      document.getElementById('camera').textContent = s.camera_state;
      document.getElementById('frames').textContent = s.recent_frame_count;
      document.getElementById('faces').textContent = s.valid_face_frames;
      document.getElementById('multiple').textContent = s.multiple_face_frames;
      document.getElementById('quality').textContent = Number(s.quality).toFixed(4);
      document.getElementById('reasons').textContent = s.reasons.length ? s.reasons.join(', ') : '正常';
    }}
    setInterval(() => refresh().catch(() => {{}}), 1000); refresh();
    document.getElementById('stop').onclick = async () => {{
      await fetch('/api/shutdown' + q, {{method:'POST'}});
      document.body.innerHTML = '<main><h1>摄像头已停止</h1></main>';
    }};
  </script>
</main></body></html>"""
