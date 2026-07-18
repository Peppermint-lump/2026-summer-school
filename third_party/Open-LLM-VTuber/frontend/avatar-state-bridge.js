(function installAvatarStateBridge() {
  "use strict";

  if (window.__avatarStateBridgeInstalled) {
    return;
  }
  window.__avatarStateBridgeInstalled = true;

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

  window.WebSocket = AvatarStateWebSocket;
})();
