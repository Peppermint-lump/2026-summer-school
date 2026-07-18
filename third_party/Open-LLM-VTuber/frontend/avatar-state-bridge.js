(function installAvatarStateBridge() {
  "use strict";

  if (window.__avatarStateBridgeInstalled) {
    return;
  }
  window.__avatarStateBridgeInstalled = true;

  const visualDebugEnabled =
    new URLSearchParams(window.location.search).get("visualDebug") === "1";

  function visualStatusPanel() {
    let panel = document.getElementById("vtuber-visual-status");
    if (panel) {
      return panel;
    }
    panel = document.createElement("div");
    panel.id = "vtuber-visual-status";
    panel.dataset.mode = visualDebugEnabled ? "debug" : "normal";
    panel.textContent = "视觉：等待首次分析";
    Object.assign(panel.style, {
      position: "fixed",
      top: "12px",
      right: "12px",
      zIndex: "2147483647",
      maxWidth: visualDebugEnabled ? "520px" : "300px",
      padding: "8px 12px",
      borderRadius: "10px",
      color: "#ecfdf5",
      background: "rgba(6, 78, 59, 0.88)",
      font: "13px/1.45 system-ui, sans-serif",
      whiteSpace: "pre-wrap",
      pointerEvents: "none",
    });
    document.body.appendChild(panel);
    return panel;
  }

  function renderVisualAnalysis(payload) {
    if (!payload || payload.source !== "continuous-video") {
      return;
    }
    const observations = payload.analysis && payload.analysis.observations;
    const video = Array.isArray(observations)
      ? observations.find((item) => item && item.modality === "video")
      : null;
    if (!video) {
      return;
    }
    const actions = Array.isArray(video.observed_actions)
      ? video.observed_actions.map((item) => item.action).filter(Boolean)
      : [];
    const actionText = actions.length ? actions.join(", ") : "无明确动作";
    const emotionText = video.fine_emotion || video.label || "uncertain";
    const reliability = Number(video.reliability || 0).toFixed(2);
    const sampledFrames =
      video.raw_metadata && video.raw_metadata.sampled_frame_count;
    const summary = `视觉：运行中｜动作：${actionText}｜情绪：${emotionText}`;
    const detail = visualDebugEnabled
      ? `\n可靠度：${reliability}｜状态：${video.status || "unknown"}` +
        `｜采样帧：${sampledFrames == null ? "未知" : sampledFrames}` +
        `\n轮次：${payload.turn_id || "unknown"}` +
        `\n轨迹：${payload.trace_directory || "未启用"}`
      : "";
    const panel = visualStatusPanel();
    panel.textContent = summary + detail;
    panel.title = payload.trace_directory || "";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", visualStatusPanel, { once: true });
  } else {
    visualStatusPanel();
  }

  const NativeWebSocket = window.WebSocket;
  function applyAvatarState(payload) {
    if (!payload || payload.type !== "avatar-state") {
      return;
    }
    window.__lastAvatarState = payload;
    const adapter = window.getLAppAdapter && window.getLAppAdapter();
    if (adapter && Number.isInteger(payload.expression_index)) {
      const expressionName = adapter.getExpressionName(payload.expression_index);
      if (expressionName) {
        adapter.setExpression(expressionName);
      }
    }
    const controller = window.xiaohudieAvatarMotionController;
    if (
      payload.motion === "greeting" &&
      controller &&
      typeof controller.playSpecialMotion === "function"
    ) {
      controller.playSpecialMotion("Greeting", 0);
    }
    if (
      payload.motion === "observe" &&
      controller &&
      typeof controller.playObserveMotion === "function"
    ) {
      controller.playObserveMotion();
    }
    if (payload.source === "continuous-video") {
      const panel = visualStatusPanel();
      panel.dataset.motion = payload.motion || "idle";
      const withoutMotion = panel.textContent
        .split("\n")
        .filter((line) => !line.startsWith("角色动作："));
      panel.textContent = withoutMotion
        .concat(`角色动作：${payload.motion || "idle"}`)
        .join("\n");
      panel.title = [
        panel.title,
        `角色动作：${payload.motion || "idle"}`,
      ].filter(Boolean).join("\n");
    }
    window.dispatchEvent(
      new CustomEvent("vtuber-avatar-state", { detail: payload }),
    );
  }

  class AvatarStateWebSocket extends NativeWebSocket {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", (event) => {
        if (typeof event.data !== "string") {
          return;
        }
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "emotion-analysis") {
            event.stopImmediatePropagation();
            window.__lastEmotionAnalysis = payload;
            renderVisualAnalysis(payload);
            window.dispatchEvent(
              new CustomEvent("vtuber-emotion-analysis", { detail: payload }),
            );
            return;
          }
          if (payload.type === "avatar-state") {
            event.stopImmediatePropagation();
            applyAvatarState(payload);
          }
        } catch (_error) {
          // The application WebSocket owns ordinary parse-error reporting.
        }
      });
    }
  }

  if (visualDebugEnabled) {
    window.__applyAvatarStateForDebug = applyAvatarState;
  }

  window.WebSocket = AvatarStateWebSocket;
})();
