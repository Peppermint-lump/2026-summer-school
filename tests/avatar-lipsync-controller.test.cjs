"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

class FakeAudio {
  constructor(source) {
    this.source = source;
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  dispatch(type) {
    for (const listener of this.listeners.get(type) || []) {
      listener();
    }
  }
}

const mouthId = { name: "ParamMouthOpenY" };
const mouthValues = [];
let releasedPcmCount = 0;
let originalStartCount = 0;
let samplesAvailable = true;

const handler = {
  _lastRms: 0.8,
  _sampleOffset: 42,
  _userTimeSeconds: 1.5,
  releasePcmData() {
    releasedPcmCount += 1;
  },
  start() {
    originalStartCount += 1;
  },
  update() {
    this._lastRms = samplesAvailable ? 0.6 : 0.4;
    return samplesAvailable;
  },
};

const model = {
  _model: {
    setParameterValueById(id, value) {
      mouthValues.push([id, value]);
    },
  },
  _lipSyncIds: {
    getSize: () => 1,
    at: () => mouthId,
  },
  _wavFileHandler: handler,
};

global.window = {
  Audio: FakeAudio,
  addEventListener: () => {},
  getLive2DManager: () => ({ getModel: () => model }),
  setInterval: () => 1,
};

require(path.resolve(
  __dirname,
  "../third_party/Open-LLM-VTuber/frontend/avatar-lipsync-controller.js",
));

const controller = window.avatarLipSyncController;
assert.equal(controller.patchNow(), true);

handler.start("first.wav");
assert.equal(originalStartCount, 1);
assert.equal(handler._lastRms, 0);
assert.equal(handler._sampleOffset, 0);
assert.equal(handler._userTimeSeconds, 0);

handler.update(0.02);
assert.equal(handler._lastRms, 0.6);

const audio = new window.Audio("first.wav");
audio.dispatch("ended");
assert.equal(handler._lastRms, 0);
assert.equal(handler._sampleOffset, 0);
assert.deepEqual(mouthValues.at(-1), [mouthId, 0]);

handler.start("second.wav");
handler.update(0.02);
assert.equal(originalStartCount, 2);
assert.equal(handler._lastRms, 0.6);

samplesAvailable = false;
handler.update(0.02);
assert.equal(handler._lastRms, 0);
assert.deepEqual(mouthValues.at(-1), [mouthId, 0]);
assert.ok(releasedPcmCount >= 3);

console.log("avatar lip-sync controller tests passed");
