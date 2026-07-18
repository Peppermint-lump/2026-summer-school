"use strict";

const assert = require("node:assert/strict");
const path = require("node:path");

let nextFrameId = 1;
let currentTimeMs = 0;
const frameCallbacks = new Map();
global.performance = { now: () => currentTimeMs };
global.window = {
  localStorage: { getItem: () => null },
  addEventListener: () => {},
  setInterval: () => 1,
  requestAnimationFrame: (callback) => {
    const id = nextFrameId++;
    frameCallbacks.set(id, callback);
    return id;
  },
  cancelAnimationFrame: (id) => frameCallbacks.delete(id),
  getLAppAdapter: () => ({
    getMgr: () => ({ _models: { getSize: () => 1 } }),
  }),
};

require(path.resolve(
  __dirname,
  "../third_party/Open-LLM-VTuber/frontend/avatar-motion-controller.js",
));

function runNextFrame(advanceMs = 16) {
  const next = frameCallbacks.entries().next();
  assert.equal(next.done, false, "expected a queued animation frame");
  const [id, callback] = next.value;
  frameCallbacks.delete(id);
  currentTimeMs += advanceMs;
  callback();
}

function makeModel() {
  const parameterValues = [0.25, -0.5, 0.75];
  const partValues = [1, 0];
  const entries = new Map();
  const events = [];
  let nextHandle = 1;

  const motionManager = {
    stopAllMotions: () => {
      entries.clear();
      events.push("queue-stopped");
    },
    isFinishedByHandle: (handle) => {
      const entry = entries.get(handle);
      return !entry || entry.finished;
    },
    getCubismMotionQueueEntry: (handle) => entries.get(handle) || null,
  };
  const core = {
    getParameterCount: () => parameterValues.length,
    getParameterValueByIndex: (index) => parameterValues[index],
    setParameterValueByIndex: (index, value) => {
      parameterValues[index] = value;
    },
    getPartCount: () => partValues.length,
    getPartOpacityByIndex: (index) => partValues[index],
    setPartOpacityByIndex: (index, value) => {
      partValues[index] = value;
    },
    saveParameters: () => events.push("saved"),
  };
  const model = {
    _model: core,
    _motionManager: motionManager,
    _modelSetting: { getMotionCount: () => 1 },
    _motions: {
      getValue: (key) => ({
        getLoopDuration: () => ({
          Greeting_0: 5,
          CatchButterfly_0: 6,
          HoldBear_0: 2.8,
        })[key],
      }),
    },
    startTapMotion: () => {},
    startMotion: (group, index, priority) => {
      const handle = nextHandle++;
      entries.set(handle, {
        isStarted: () => true,
        finished: false,
      });
      events.push(["motion", group, index, priority, handle]);
      parameterValues.fill(9);
      partValues.fill(0.5);
      return handle;
    },
    setExpression: (name) => events.push(["expression", name]),
    startRandomMotion: (group, priority) => {
      events.push(["idle", group, priority]);
    },
  };
  return {
    model,
    parameterValues,
    partValues,
    entries,
    events,
    finish(handle) {
      entries.get(handle).finished = true;
    },
  };
}

async function flushMicrotasks() {
  await Promise.resolve();
  await Promise.resolve();
}

async function finishMotionAndTransition(fixture, handle, displayMs) {
  fixture.finish(handle);
  runNextFrame(displayMs);
  await flushMicrotasks();
  runNextFrame(250);
  const midwayParameters = [...fixture.parameterValues];
  runNextFrame(250);
  await flushMicrotasks();
  return midwayParameters;
}

async function testMotionWaitsForItsQueueEntry() {
  const fixture = makeModel();
  const controller = window.xiaohudieAvatarMotionController;
  controller.attach(fixture.model);
  fixture.model.startTapMotion("HitAreaBody", {
    HitAreaBody: { HoldBear: 1 },
  });

  const handle = controller.activeSpecialMotion.queueHandle;
  runNextFrame();
  runNextFrame();
  assert.deepEqual(fixture.parameterValues, [9, 9, 9]);
  assert.equal(controller.state, "special-motion");

  fixture.finish(handle);
  runNextFrame(1000);
  assert.deepEqual(fixture.parameterValues, [9, 9, 9]);
  assert.equal(controller.state, "special-motion");

  runNextFrame(2000);
  await flushMicrotasks();
  runNextFrame(250);
  assert.ok(fixture.parameterValues.every((value) => value < 9));
  assert.notDeepEqual(fixture.parameterValues, [0.25, -0.5, 0.75]);
  runNextFrame(250);
  await flushMicrotasks();

  assert.deepEqual(fixture.parameterValues, [0.25, -0.5, 0.75]);
  assert.deepEqual(fixture.partValues, [1, 0]);
  assert.deepEqual(fixture.events.slice(-2), [
    ["expression", "neutral"],
    ["idle", "Idle", 1],
  ]);
  assert.equal(controller.state, "idle");
}

async function testLatestMotionStopsAndReplacesPreviousMotion() {
  const fixture = makeModel();
  const controller = window.xiaohudieAvatarMotionController;
  controller.attach(fixture.model);

  controller.playSpecialMotion("Greeting", 0);
  const firstHandle = controller.activeSpecialMotion.queueHandle;
  runNextFrame();

  controller.playSpecialMotion("CatchButterfly", 0);
  const secondHandle = controller.activeSpecialMotion.queueHandle;
  assert.notEqual(firstHandle, secondHandle);
  assert.equal(fixture.entries.has(firstHandle), false);
  assert.equal(fixture.entries.has(secondHandle), true);
  assert.deepEqual(fixture.parameterValues, [9, 9, 9]);

  runNextFrame();
  fixture.finish(secondHandle);
  const midwayParameters = await finishMotionAndTransition(
    fixture,
    secondHandle,
    6000,
  );
  assert.notDeepEqual(midwayParameters, [9, 9, 9]);
  assert.notDeepEqual(midwayParameters, [0.25, -0.5, 0.75]);
  assert.deepEqual(fixture.parameterValues, [0.25, -0.5, 0.75]);
  assert.equal(
    fixture.events.filter(
      (event) => Array.isArray(event) && event[0] === "idle",
    ).length,
    1,
  );
}

async function testRepeatedMotionRestartsFromBeginning() {
  const fixture = makeModel();
  const controller = window.xiaohudieAvatarMotionController;
  controller.attach(fixture.model);

  controller.playSpecialMotion("Greeting", 0);
  const firstHandle = controller.activeSpecialMotion.queueHandle;
  controller.playSpecialMotion("Greeting", 0);
  const secondHandle = controller.activeSpecialMotion.queueHandle;

  assert.notEqual(firstHandle, secondHandle);
  assert.equal(fixture.entries.has(firstHandle), false);
  assert.equal(fixture.entries.has(secondHandle), true);
}

async function testRapidSequenceLeavesOnlyNewestMotion() {
  const fixture = makeModel();
  const controller = window.xiaohudieAvatarMotionController;
  controller.attach(fixture.model);

  controller.playSpecialMotion("Greeting", 0);
  controller.playSpecialMotion("CatchButterfly", 0);
  controller.playSpecialMotion("HoldBear", 0);

  assert.equal(fixture.entries.size, 1);
  const active = controller.activeSpecialMotion;
  assert.equal(active.group, "HoldBear");
  assert.equal(fixture.entries.has(active.queueHandle), true);
}

async function testExpressionDoesNotInterruptSpecialMotion() {
  const fixture = makeModel();
  const controller = window.xiaohudieAvatarMotionController;
  controller.attach(fixture.model);

  controller.playSpecialMotion("HoldBear", 0);
  const handle = controller.activeSpecialMotion.queueHandle;
  fixture.model.setExpression("heart");

  assert.equal(controller.activeSpecialMotion.queueHandle, handle);
  assert.equal(fixture.entries.has(handle), true);
  assert.equal(controller.state, "special-motion");
}

async function testConfiguredMinimumDisplayDurations() {
  const fixture = makeModel();
  const controller = window.xiaohudieAvatarMotionController;
  controller.attach(fixture.model);

  controller.playSpecialMotion("Greeting", 0);
  assert.equal(controller.activeSpecialMotion.minimumDisplayDurationMs, 5000);
  controller.playSpecialMotion("CatchButterfly", 0);
  assert.equal(controller.activeSpecialMotion.minimumDisplayDurationMs, 6000);
  controller.playSpecialMotion("HoldBear", 0);
  assert.equal(controller.activeSpecialMotion.minimumDisplayDurationMs, 3000);
  controller.destroy("duration test teardown");
}

async function testNewMotionInterruptsIdleTransition() {
  const fixture = makeModel();
  const controller = window.xiaohudieAvatarMotionController;
  controller.attach(fixture.model);
  controller.playSpecialMotion("HoldBear", 0);
  const handle = controller.activeSpecialMotion.queueHandle;
  runNextFrame();
  fixture.finish(handle);
  runNextFrame(3000);
  await flushMicrotasks();
  runNextFrame(250);
  assert.equal(controller.state, "resetting");

  controller.playSpecialMotion("Greeting", 0);
  assert.equal(controller.state, "special-motion");
  assert.equal(controller.activeSpecialMotion.group, "Greeting");
  assert.deepEqual(fixture.parameterValues, [9, 9, 9]);
  controller.destroy("transition interruption test teardown");
}

async function testDestroyStopsMotionAndCancelsPolling() {
  const fixture = makeModel();
  const controller = window.xiaohudieAvatarMotionController;
  controller.attach(fixture.model);
  controller.playSpecialMotion("Greeting", 0);

  controller.destroy("test teardown");

  assert.equal(fixture.entries.size, 0);
  assert.equal(controller.activeSpecialMotion, null);
  assert.equal(controller.model, null);
}

(async function run() {
  await testMotionWaitsForItsQueueEntry();
  await testLatestMotionStopsAndReplacesPreviousMotion();
  await testRepeatedMotionRestartsFromBeginning();
  await testRapidSequenceLeavesOnlyNewestMotion();
  await testExpressionDoesNotInterruptSpecialMotion();
  await testConfiguredMinimumDisplayDurations();
  await testNewMotionInterruptsIdleTransition();
  await testDestroyStopsMotionAndCancelsPolling();
  console.log("avatar motion controller tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
