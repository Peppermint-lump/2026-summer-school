"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

let now = 0;
let nextFrameId = 1;
const frames = new Map();

global.performance = { now: () => now };
global.window = {
  localStorage: { getItem: () => null },
  setInterval: () => 0,
  addEventListener: () => undefined,
  requestAnimationFrame(callback) {
    const frameId = nextFrameId;
    nextFrameId += 1;
    frames.set(frameId, callback);
    return frameId;
  },
  cancelAnimationFrame(frameId) {
    frames.delete(frameId);
  },
  getLAppAdapter: () => null,
};

function runNextFrame(at) {
  now = at;
  const next = frames.entries().next();
  assert.equal(next.done, false, `expected an animation frame at ${at}ms`);
  const [frameId, callback] = next.value;
  frames.delete(frameId);
  callback();
}

const sourcePath = path.resolve(__dirname, "../frontend/avatar-motion-controller.js");
eval(fs.readFileSync(sourcePath, "utf8"));

const parameterIds = new Map([
  ["ParamAngleY", 0],
  ["ParamBodyAngleY", 1],
]);
const parameters = [3, -2, 0.5];
const parts = [1];
let idleStarts = 0;
const core = {
  getParameterCount: () => parameters.length,
  getParameterIndex: (id) => parameterIds.get(id) ?? -1,
  getParameterValueByIndex: (index) => parameters[index],
  setParameterValueByIndex: (index, value) => {
    parameters[index] = value;
  },
  getPartCount: () => parts.length,
  getPartOpacityByIndex: (index) => parts[index],
  setPartOpacityByIndex: (index, value) => {
    parts[index] = value;
  },
  saveParameters: () => undefined,
};
const model = {
  _model: core,
  _modelSetting: { getMotionCount: () => 1 },
  _motionManager: { stopAllMotions: () => undefined },
  startTapMotion: () => undefined,
  startRandomMotion: () => {
    idleStarts += 1;
  },
};

const controller = window.xiaohudieAvatarMotionController;
controller.attach(model);
controller.playObserveMotion();
assert.equal(controller.state, "observe-motion");
assert.equal(controller.activeSpecialMotion.group, "Observe");

runNextFrame(600);
assert.notEqual(parameters[0], 3, "observe should change ParamAngleY");
assert.notEqual(parameters[1], -2, "observe should change ParamBodyAngleY");
runNextFrame(1440);
runNextFrame(2400);

assert.equal(controller.state, "idle");
assert.equal(controller.activeSpecialMotion, null);
assert.equal(parameters[0], 3, "observe must restore head baseline");
assert.equal(parameters[1], -2, "observe must restore body baseline");
assert.equal(idleStarts, 1, "observe must restart Idle exactly once");
assert.equal(frames.size, 0, "observe must leave no animation frame behind");

console.log("avatar observe motion lifecycle: ok");
