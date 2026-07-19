"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const bridgeSource = fs.readFileSync(
  path.resolve(
    __dirname,
    "../third_party/Open-LLM-VTuber/frontend/avatar-state-bridge.js",
  ),
  "utf8",
);

function installBridge(search) {
  const elements = new Map();
  const appended = [];
  const dispatched = [];
  const controllerCalls = [];

  class FakeWebSocket {
    constructor() {
      this.listeners = new Map();
    }

    addEventListener(type, listener) {
      const listeners = this.listeners.get(type) || [];
      listeners.push(listener);
      this.listeners.set(type, listeners);
    }

    receive(payload) {
      const event = {
        data: JSON.stringify(payload),
        stopImmediatePropagation() {},
      };
      for (const listener of this.listeners.get("message") || []) {
        listener(event);
      }
    }
  }

  class FakeCustomEvent {
    constructor(type, options) {
      this.type = type;
      this.detail = options.detail;
    }
  }

  const document = {
    readyState: "complete",
    getElementById: (id) => elements.get(id) || null,
    createElement: () => ({ dataset: {}, style: {}, textContent: "", title: "" }),
    addEventListener() {},
    body: {
      appendChild(element) {
        elements.set(element.id, element);
        appended.push(element);
      },
    },
  };
  const window = {
    location: { search },
    WebSocket: FakeWebSocket,
    getLAppAdapter: () => null,
    xiaohudieAvatarMotionController: {
      playSpecialMotion: (...args) => controllerCalls.push(["special", ...args]),
      playObserveMotion: (...args) => controllerCalls.push(["observe", ...args]),
    },
    dispatchEvent: (event) => dispatched.push(event),
  };
  const context = vm.createContext({
    window,
    document,
    URLSearchParams,
    CustomEvent: FakeCustomEvent,
  });
  vm.runInContext(bridgeSource, context);

  return { window, elements, appended, dispatched, controllerCalls };
}

function videoAnalysisPayload() {
  return {
    type: "emotion-analysis",
    source: "continuous-video",
    turn_id: "visual_test",
    trace_directory: "runtime/debug/emotion_turns/visual_test",
    analysis: {
      observations: [
        {
          modality: "video",
          label: "positive",
          fine_emotion: "happy",
          status: "ok",
          reliability: 0.82,
          observed_actions: [{ action: "wave" }],
          raw_metadata: { sampled_frame_count: 6 },
        },
      ],
    },
  };
}

function avatarStatePayload() {
  return {
    type: "avatar-state",
    source: "continuous-video",
    motion: "observe",
    expression_suppressed: false,
  };
}

function testFormalModeHidesOverlayButKeepsVisualBehavior() {
  const fixture = installBridge("");
  assert.equal(fixture.appended.length, 0);

  const socket = new fixture.window.WebSocket("ws://127.0.0.1");
  socket.receive(videoAnalysisPayload());
  socket.receive(avatarStatePayload());

  assert.equal(fixture.elements.has("vtuber-visual-status"), false);
  assert.equal(fixture.window.__lastEmotionAnalysis.turn_id, "visual_test");
  assert.equal(fixture.window.__lastAvatarState.motion, "observe");
  assert.deepEqual(fixture.controllerCalls, [["observe"]]);
  assert.deepEqual(
    fixture.dispatched.map((event) => event.type),
    ["vtuber-emotion-analysis", "vtuber-avatar-state"],
  );
}

function testDebugModeShowsFullOverlay() {
  const fixture = installBridge("?visualDebug=1");
  assert.equal(fixture.appended.length, 1);

  const socket = new fixture.window.WebSocket("ws://127.0.0.1");
  socket.receive(videoAnalysisPayload());
  socket.receive(avatarStatePayload());

  const panel = fixture.elements.get("vtuber-visual-status");
  assert.equal(panel.dataset.mode, "debug");
  assert.equal(panel.dataset.motion, "observe");
  assert.match(panel.textContent, /动作：wave/);
  assert.match(panel.textContent, /情绪：happy/);
  assert.match(panel.textContent, /可靠度：0\.82/);
  assert.match(panel.textContent, /轮次：visual_test/);
  assert.match(panel.textContent, /角色动作：observe/);
  assert.match(panel.textContent, /融合表情保护：关闭/);
}

testFormalModeHidesOverlayButKeepsVisualBehavior();
testDebugModeShowsFullOverlay();
console.log("avatar-state-bridge tests passed");
