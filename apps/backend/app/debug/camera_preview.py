# ruff: noqa: E501
"""Loopback-only MJPEG preview for validating the current camera pipeline."""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol, cast
from urllib.parse import parse_qs, urlsplit

import cv2

from apps.backend.app.capture.camera_buffer import CameraBuffer, CameraState
from apps.backend.app.emotion.video.face_quality import FaceQualityEvaluator


class TurnAnalyzer(Protocol):
    def analyze(
        self,
        *,
        duration_seconds: float,
        transcript: str | None,
        progress: Callable[[str], None],
    ) -> dict[str, Any]: ...


class CameraPreviewApplication:
    def __init__(
        self,
        camera: CameraBuffer,
        evaluator: FaceQualityEvaluator,
        *,
        status_window_seconds: float = 3.0,
        analyzer: TurnAnalyzer | None = None,
        analysis_unavailable_reason: str | None = None,
    ) -> None:
        if status_window_seconds <= 0:
            raise ValueError("status_window_seconds must be positive")
        self.camera = camera
        self.evaluator = evaluator
        self.status_window_seconds = status_window_seconds
        self.shutdown_event = threading.Event()
        self._analyzer = analyzer
        self._analysis_unavailable_reason = analysis_unavailable_reason
        self._analysis_lock = threading.Lock()
        self._analysis_state = "idle"
        self._analysis_result: dict[str, Any] | None = None
        self._analysis_error: str | None = None
        self._analysis_started_ms: int | None = None
        self._analysis_finished_ms: int | None = None

    def status(self) -> dict[str, Any]:
        now_ms = time.time_ns() // 1_000_000
        frames = self.camera.frames_between(
            now_ms - int(self.status_window_seconds * 1000), now_ms
        )
        report = self.evaluator.evaluate(frames)
        pipeline_receiving = bool(frames) and self.camera.state is CameraState.RUNNING
        status = {
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
            "retained_media": False,
        }
        status.update(self.analysis_status())
        return status

    def analysis_status(self) -> dict[str, Any]:
        with self._analysis_lock:
            return {
                "analysis_available": self._analyzer is not None,
                "analysis_unavailable_reason": self._analysis_unavailable_reason,
                "analysis_state": self._analysis_state,
                "analysis_result": self._analysis_result,
                "analysis_error": self._analysis_error,
                "analysis_started_ms": self._analysis_started_ms,
                "analysis_finished_ms": self._analysis_finished_ms,
            }

    def start_analysis(
        self, *, duration_seconds: float, transcript: str | None
    ) -> bool:
        if self._analyzer is None:
            raise RuntimeError(
                self._analysis_unavailable_reason or "provider analysis is unavailable"
            )
        if not 1.0 <= duration_seconds <= 15.0:
            raise ValueError("duration_seconds must be between 1 and 15")
        if transcript is not None and len(transcript) > 4000:
            raise ValueError("transcript must not exceed 4000 characters")
        with self._analysis_lock:
            if self._analysis_state in {
                "queued",
                "capturing",
                "preprocessing",
                "provider_analysis",
                "fusion",
            }:
                return False
            self._analysis_state = "queued"
            self._analysis_result = None
            self._analysis_error = None
            self._analysis_started_ms = time.time_ns() // 1_000_000
            self._analysis_finished_ms = None
        threading.Thread(
            target=self._run_analysis,
            kwargs={
                "duration_seconds": duration_seconds,
                "transcript": transcript,
            },
            daemon=True,
            name="emotion-debug-analysis",
        ).start()
        return True

    def _run_analysis(
        self,
        *,
        duration_seconds: float,
        transcript: str | None,
    ) -> None:
        assert self._analyzer is not None
        try:
            result = self._analyzer.analyze(
                duration_seconds=duration_seconds,
                transcript=transcript,
                progress=self._set_analysis_state,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            with self._analysis_lock:
                self._analysis_state = "failed"
                self._analysis_error = str(exc)
                self._analysis_finished_ms = time.time_ns() // 1_000_000
            return
        with self._analysis_lock:
            self._analysis_result = result
            self._analysis_state = "completed"
            self._analysis_finished_ms = time.time_ns() // 1_000_000

    def _set_analysis_state(self, state: str) -> None:
        with self._analysis_lock:
            self._analysis_state = state

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
        if parsed.path == "/api/analyze":
            self._start_analysis()
            return
        if parsed.path != "/api/shutdown":
            self._send_json({"status": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        self._send_json({"status": "stopping"})
        self.server.application.shutdown_event.set()
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _start_analysis(self) -> None:
        try:
            payload = self._read_json_body()
            duration = payload.get("duration_seconds", 5.0)
            transcript = payload.get("transcript")
            if isinstance(duration, bool) or not isinstance(duration, (int, float)):
                raise ValueError("duration_seconds must be numeric")
            if transcript is not None and not isinstance(transcript, str):
                raise ValueError("transcript must be text or null")
            accepted = self.server.application.start_analysis(
                duration_seconds=float(duration),
                transcript=transcript,
            )
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            self._send_json(
                {"status": "invalid_request", "message": str(exc)},
                HTTPStatus.BAD_REQUEST,
            )
            return
        except RuntimeError as exc:
            self._send_json(
                {"status": "unavailable", "message": str(exc)},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return
        if not accepted:
            self._send_json(
                {"status": "analysis_in_progress"},
                HTTPStatus.CONFLICT,
            )
            return
        self._send_json({"status": "accepted"}, HTTPStatus.ACCEPTED)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0 or content_length > 16_384:
            raise ValueError("request body must be between 1 and 16384 bytes")
        parsed = json.loads(self.rfile.read(content_length).decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return cast(dict[str, Any], parsed)

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
  <title>情绪与动作完整链路调试</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; background: #10131a; color: #eef2ff; }}
    main {{ max-width: 1280px; margin: auto; padding: 24px; }}
    h1 {{ margin: 0 0 6px; font-size: 26px; }}
    .note {{ color: #aab4ca; margin-bottom: 18px; }}
    .layout {{ display: grid; grid-template-columns: minmax(0,2fr) minmax(280px,1fr); gap: 18px; }}
    .card {{ background: #181d28; border: 1px solid #2b3446; border-radius: 14px; padding: 16px; }}
    img {{ width: 100%; aspect-ratio: 4/3; object-fit: cover; background: #050609; border-radius: 10px; transform: scaleX(-1); }}
    .status {{ display: flex; justify-content: space-between; gap: 12px; padding: 10px 0; border-bottom: 1px solid #2b3446; }}
    .status:last-child {{ border: 0; }} .value {{ text-align: right; }}
    .ok {{ color: #65e6a4; }} .warn {{ color: #ffc76a; }} .bad {{ color: #ff7b8c; }}
    .analysis {{ margin-top: 18px; }}
    .controls {{ display: grid; grid-template-columns: 140px 1fr; gap: 12px; align-items: center; }}
    input, textarea {{ box-sizing: border-box; width: 100%; padding: 10px; color: #eef2ff; background: #10141d; border: 1px solid #39455c; border-radius: 8px; }}
    textarea {{ min-height: 72px; resize: vertical; }}
    label.consent {{ display: flex; gap: 9px; align-items: flex-start; color: #ffc76a; margin: 14px 0; }}
    label.consent input {{ width: auto; margin-top: 4px; }}
    button {{ width: 100%; padding: 11px; border: 0; border-radius: 9px; background: #5b7cfa; color: white; cursor: pointer; }}
    button:disabled {{ opacity: .45; cursor: not-allowed; }} #stop {{ margin-top: 12px; background: #d95367; }}
    .results {{ display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; margin-top: 14px; }}
    .result {{ background: #111722; border-radius: 10px; padding: 13px; min-height: 92px; }}
    .result h3 {{ margin: 0 0 8px; color: #aab4ca; font-size: 14px; }}
    .primary {{ font-size: 21px; font-weight: 700; }} .detail {{ color: #aab4ca; margin-top: 6px; font-size: 13px; overflow-wrap: anywhere; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; max-height: 420px; overflow: auto; background: #0d1119; border-radius: 9px; padding: 12px; color: #cbd5e9; }}
    @media (max-width:760px) {{ .layout {{ grid-template-columns: 1fr; }} }}
    @media (max-width:900px) {{ .results {{ grid-template-columns: 1fr; }} }}
  </style>
</head><body><main>
  <h1>情绪与动作完整链路调试</h1>
  <div class="note">实时预览不上传；只有点击“开始云端分析”后，当前轮次的有序采样帧才会发送给配置的 Provider。临时帧分析后删除。</div>
  <div class="layout"><section class="card"><img id="preview" alt="实时摄像头预览"></section>
  <aside class="card">
    <div class="status"><span>视频管线</span><strong id="pipeline" class="warn">等待帧</strong></div>
    <div class="status"><span>摄像头</span><span id="camera" class="value">—</span></div>
    <div class="status"><span>近 3 秒帧数</span><span id="frames" class="value">0</span></div>
    <div class="status"><span>有效人脸帧</span><span id="faces" class="value">0</span></div>
    <div class="status"><span>多人帧</span><span id="multiple" class="value">0</span></div>
    <div class="status"><span>画面质量</span><span id="quality" class="value">0</span></div>
    <div class="status"><span>质量原因</span><span id="reasons" class="value">—</span></div>
    <div class="status"><span>分析状态</span><strong id="analysisState" class="warn">空闲</strong></div>
    <div class="status"><span>原始媒体留存</span><span class="ok">否</span></div>
    <button id="stop">停止摄像头和服务器</button>
  </aside></div>
  <section class="card analysis">
    <h2>启动一次分析轮次</h2>
    <div class="controls">
      <label for="duration">采集时长（秒）</label><input id="duration" type="number" min="1" max="15" step="1" value="5">
      <label for="transcript">本轮文字（可选）</label><textarea id="transcript" maxlength="4000" placeholder="当前没有 ASR，可手动输入一句话来验证文字情绪与融合；留空则只验证视频。"></textarea>
    </div>
    <label class="consent"><input id="consent" type="checkbox"><span>我确认本轮有序摄像头采样帧会上传至 MiMo，并可能产生 API 费用；如填写文字，它会独立发送给 GLM。</span></label>
    <button id="analyze" disabled>开始 5 秒云端分析（请在倒计时内挥手/微笑）</button>
    <div id="availability" class="detail">正在检查 Provider 配置…</div>
    <div class="results">
      <div class="result"><h3>动作识别</h3><div id="action" class="primary">—</div><div id="actionDetail" class="detail">等待分析</div></div>
      <div class="result"><h3>视频情绪</h3><div id="videoEmotion" class="primary">—</div><div id="videoDetail" class="detail">等待分析</div></div>
      <div class="result"><h3>文字情绪</h3><div id="textEmotion" class="primary">—</div><div id="textDetail" class="detail">可选，不含声音</div></div>
      <div class="result"><h3>最终融合情绪</h3><div id="fusionEmotion" class="primary">—</div><div id="fusionDetail" class="detail">至少两个可靠模态才产生确定融合</div></div>
      <div class="result"><h3>冲突与策略</h3><div id="conflict" class="primary">—</div><div id="strategy" class="detail">等待分析</div></div>
      <div class="result"><h3>分步调试目录</h3><div id="trace" class="detail">完成后显示绝对路径</div></div>
    </div>
    <details><summary>完整结构化结果</summary><pre id="raw">尚未分析</pre></details>
  </section>
  <script>
    const token = {safe_token}; const q = `?token=${{encodeURIComponent(token)}}`;
    const names = {{positive:'积极/开心', neutral:'中性', negative:'消极', uncertain:'不确定', wave:'挥手 wave', thumbs_up:'点赞 thumbs_up', clap:'拍手 clap', nod:'点头 nod', head_shake:'摇头 head_shake', hands_up:'举手 hands_up', point:'指向 point', still:'静止 still', other:'其他 other'}};
    const stateNames = {{idle:'空闲', queued:'已排队', capturing:'采集中，请做动作', preprocessing:'正在检查并采样帧', provider_analysis:'Provider 正在分析', fusion:'正在加权融合', completed:'完成', failed:'失败'}};
    document.getElementById('preview').src = '/stream.mjpg' + q;
    const analyze = document.getElementById('analyze'); const consent = document.getElementById('consent');
    consent.onchange = () => {{ analyze.disabled = !consent.checked || analyze.dataset.available !== 'true'; }};
    document.getElementById('duration').oninput = (event) => {{ analyze.textContent = `开始 ${{event.target.value || 5}} 秒云端分析（请在倒计时内挥手/微笑）`; }};
    function fixed(value) {{ return Number(value || 0).toFixed(4); }}
    function renderResult(result) {{
      if (!result) return;
      const actions = result.video.observed_actions || [];
      document.getElementById('action').textContent = actions.length ? actions.map(a => names[a.type] || a.type).join('、') : '未识别到标准动作';
      document.getElementById('actionDetail').textContent = actions.length ? actions.map(a => `${{a.type}} confidence=${{fixed(a.confidence)}}；${{a.evidence || '无证据说明'}}`).join(' | ') : `status=${{result.video.status}}`;
      document.getElementById('videoEmotion').textContent = names[result.video.label] || result.video.label;
      document.getElementById('videoDetail').textContent = `fine=${{result.video.fine_emotion || '—'}} | confidence=${{fixed(result.video.confidence)}} | quality=${{fixed(result.video.quality)}} | reliability=${{fixed(result.video.reliability)}}`;
      document.getElementById('textEmotion').textContent = names[result.text.label] || result.text.label;
      document.getElementById('textDetail').textContent = `status=${{result.text.status}} | confidence=${{fixed(result.text.confidence)}} | reliability=${{fixed(result.text.reliability)}}`;
      document.getElementById('fusionEmotion').textContent = names[result.fusion.final_emotion] || result.fusion.final_emotion;
      document.getElementById('fusionDetail').textContent = `weighted_score=${{fixed(result.fusion.weighted_score)}} | reliable=${{result.fusion.reliable_modalities.join(', ') || '无'}}`;
      document.getElementById('conflict').textContent = result.fusion.conflict_type;
      document.getElementById('strategy').textContent = `strategy=${{result.fusion.strategy}}；${{result.fusion.explanation}}`;
      document.getElementById('trace').textContent = result.trace_directory;
      document.getElementById('raw').textContent = JSON.stringify(result, null, 2);
    }}
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
      const state = document.getElementById('analysisState');
      state.textContent = stateNames[s.analysis_state] || s.analysis_state;
      state.className = s.analysis_state === 'completed' ? 'ok' : (s.analysis_state === 'failed' ? 'bad' : 'warn');
      analyze.dataset.available = String(s.analysis_available);
      analyze.disabled = !consent.checked || !s.analysis_available || ['queued','capturing','preprocessing','provider_analysis','fusion'].includes(s.analysis_state);
      document.getElementById('availability').textContent = s.analysis_available ? 'Provider 已配置。声音未接入，本轮只包含视频和可选文字。' : `分析不可用：${{s.analysis_unavailable_reason || '请检查 .env'}}`;
      if (s.analysis_error) document.getElementById('raw').textContent = `分析失败：${{s.analysis_error}}`;
      renderResult(s.analysis_result);
    }}
    setInterval(() => refresh().catch(() => {{}}), 1000); refresh();
    analyze.onclick = async () => {{
      analyze.disabled = true;
      const response = await fetch('/api/analyze' + q, {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{duration_seconds:Number(document.getElementById('duration').value), transcript:document.getElementById('transcript').value || null}})}});
      const result = await response.json();
      if (!response.ok) document.getElementById('raw').textContent = `无法启动：${{result.message || result.status}}`;
      refresh();
    }};
    document.getElementById('stop').onclick = async () => {{
      await fetch('/api/shutdown' + q, {{method:'POST'}});
      document.body.innerHTML = '<main><h1>摄像头已停止</h1></main>';
    }};
  </script>
</main></body></html>"""
