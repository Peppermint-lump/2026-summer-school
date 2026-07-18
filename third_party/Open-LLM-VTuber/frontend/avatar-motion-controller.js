(function () {
  "use strict";

  if (window.__xiaohudieMotionControllerInstalled) {
    return;
  }
  window.__xiaohudieMotionControllerInstalled = true;

  const MOTION_PRIORITY = Object.freeze({
    IDLE: 1,
    NORMAL: 2,
    SPECIAL: 3,
  });
  const SPECIAL_MOTION_GROUPS = new Set([
    "Greeting",
    "CatchButterfly",
    "HoldBear",
  ]);
  const SPECIAL_MOTION_DISPLAY_MS = Object.freeze({
    Greeting: 5000,
    CatchButterfly: 6000,
    HoldBear: 3000,
  });
  const IDLE_TRANSITION_DURATION_MS = 500;
  const IDLE_GROUP = "Idle";
  const NEUTRAL_EXPRESSION = "neutral";
  const INVALID_MOTION_HANDLE = -1;
  const DEBUG_KEY = "live2dDebug";

  function debug(message, details) {
    if (window.localStorage.getItem(DEBUG_KEY) === "true") {
      console.debug(`[Live2D] ${message}`, details || "");
    }
  }

  function chooseWeightedMotion(hitArea, tapMotions) {
    let candidates = tapMotions && tapMotions[hitArea];
    if (!candidates || Object.keys(candidates).length === 0) {
      candidates = {};
      Object.values(tapMotions || {}).forEach(function (mapping) {
        Object.entries(mapping).forEach(function ([group, weight]) {
          candidates[group] = (candidates[group] || 0) + Number(weight || 0);
        });
      });
    }

    const entries = Object.entries(candidates).filter(function ([group, weight]) {
      return SPECIAL_MOTION_GROUPS.has(group) && Number(weight) > 0;
    });
    const total = entries.reduce(function (sum, [, weight]) {
      return sum + Number(weight);
    }, 0);
    let cursor = Math.random() * total;
    for (const [group, weight] of entries) {
      cursor -= Number(weight);
      if (cursor < 0) {
        return group;
      }
    }
    return entries.length > 0 ? entries[entries.length - 1][0] : null;
  }

  function supportsSpecialMotionLifecycle(model) {
    const setting = model && model._modelSetting;
    if (!setting || typeof setting.getMotionCount !== "function") {
      return false;
    }
    return Array.from(SPECIAL_MOTION_GROUPS).every(function (group) {
      return setting.getMotionCount(group) > 0;
    });
  }

  class AvatarMotionController {
    constructor() {
      this.model = null;
      this.originalStartTapMotion = null;
      this.motionToken = 0;
      this.state = "idle";
      this.baseline = null;
      this.activeSpecialMotion = null;
    }

    transitionTo(next, reason) {
      debug("state transition", {
        from: this.state,
        to: next,
        reason,
        token: this.motionToken,
        activeMotion: this.describeActiveMotion(),
      });
      this.state = next;
    }

    describeActiveMotion() {
      const active = this.activeSpecialMotion;
      if (!active) {
        return null;
      }
      return {
        token: active.token,
        group: active.group,
        index: active.index,
        queueHandle: active.queueHandle,
        expectedDurationMs: active.expectedDurationMs,
        minimumDisplayDurationMs: active.minimumDisplayDurationMs,
      };
    }

    attach(model) {
      if (!model || this.model === model) {
        return;
      }

      if (this.model) {
        if (this.originalStartTapMotion) {
          this.cancelActiveSpecialMotion({
            reason: "model switched",
            resetParameters: false,
            startIdle: false,
          });
          this.model.startTapMotion = this.originalStartTapMotion;
        }
      }

      this.model = model;
      this.motionToken += 1;
      this.baseline = null;
      this.activeSpecialMotion = null;
      this.transitionTo("idle", "controller attached");
      this.originalStartTapMotion = null;

      if (!supportsSpecialMotionLifecycle(model)) {
        debug("controller bypassed for model without Xiaohudie motions", { model });
        return;
      }

      this.originalStartTapMotion = model.startTapMotion.bind(model);

      const controller = this;
      model.startTapMotion = function (hitArea, tapMotions) {
        const group = chooseWeightedMotion(hitArea, tapMotions);
        if (group) {
          void controller.playSpecialMotion(group);
        }
      };

      const adapter = window.getLAppAdapter && window.getLAppAdapter();
      const manager = adapter && adapter.getMgr && adapter.getMgr();
      const modelCount = manager && manager._models && manager._models.getSize
        ? manager._models.getSize()
        : 1;
      debug("controller attached", { model, modelCount });
    }

    captureBaseline() {
      const core = this.model && this.model._model;
      if (!core) {
        return null;
      }
      const parameters = [];
      for (let index = 0; index < core.getParameterCount(); index += 1) {
        parameters.push(core.getParameterValueByIndex(index));
      }
      const parts = [];
      for (let index = 0; index < core.getPartCount(); index += 1) {
        parts.push(core.getPartOpacityByIndex(index));
      }
      return { parameters, parts };
    }

    restoreBaseline(reason) {
      const core = this.model && this.model._model;
      if (!core || !this.baseline) {
        return;
      }
      const before = this.captureBaseline();
      this.applySnapshot(this.baseline);
      debug("special state restored", {
        reason,
        before,
        after: this.baseline,
      });
    }

    applySnapshot(snapshot) {
      const core = this.model && this.model._model;
      if (!core || !snapshot) {
        return;
      }
      snapshot.parameters.forEach(function (value, index) {
        core.setParameterValueByIndex(index, value);
      });
      snapshot.parts.forEach(function (value, index) {
        core.setPartOpacityByIndex(index, value);
      });
      core.saveParameters();
    }

    fadeToBaseline(active, reason) {
      const from = this.captureBaseline();
      const target = this.baseline;
      if (!from || !target) {
        this.restoreBaseline(reason);
        return Promise.resolve({ status: "completed" });
      }

      const startedAt = performance.now();
      return new Promise((resolve) => {
        active.resolveTransition = resolve;

        const renderTransitionFrame = () => {
          if (
            active.token !== this.motionToken ||
            this.activeSpecialMotion !== active
          ) {
            active.animationFrame = null;
            active.resolveTransition = null;
            resolve({ status: "cancelled" });
            return;
          }

          const elapsedMs = performance.now() - startedAt;
          const progress = Math.min(elapsedMs / IDLE_TRANSITION_DURATION_MS, 1);
          const easedProgress = progress * progress * (3 - 2 * progress);
          const snapshot = {
            parameters: target.parameters.map(function (value, index) {
              return from.parameters[index] +
                (value - from.parameters[index]) * easedProgress;
            }),
            parts: target.parts.map(function (value, index) {
              return from.parts[index] +
                (value - from.parts[index]) * easedProgress;
            }),
          };
          this.applySnapshot(snapshot);

          if (progress >= 1) {
            active.animationFrame = null;
            active.resolveTransition = null;
            debug("Idle transition completed", {
              reason,
              durationMs: elapsedMs,
            });
            resolve({ status: "completed", elapsedMs });
            return;
          }

          active.animationFrame = window.requestAnimationFrame(
            renderTransitionFrame,
          );
        };

        active.animationFrame = window.requestAnimationFrame(
          renderTransitionFrame,
        );
      });
    }

    stopMotionQueue(reason) {
      const motionManager = this.model && this.model._motionManager;
      if (motionManager && motionManager.stopAllMotions) {
        motionManager.stopAllMotions();
        debug("motion queue stopped", { reason });
      }
    }

    motionDurationMs(group, index) {
      const motions = this.model && this.model._motions;
      const motion = motions && motions.getValue
        ? motions.getValue(`${group}_${index}`)
        : null;
      const duration = motion && motion.getLoopDuration
        ? motion.getLoopDuration()
        : 0;
      return duration > 0 ? duration * 1000 : null;
    }

    cancelActiveSpecialMotion(options) {
      const active = this.activeSpecialMotion;
      this.motionToken += 1;

      if (active && active.animationFrame !== null) {
        window.cancelAnimationFrame(active.animationFrame);
        active.animationFrame = null;
      }
      if (active && active.resolveCompletion) {
        active.resolveCompletion({
          status: "interrupted",
          reason: options.reason,
        });
        active.resolveCompletion = null;
      }
      if (active && active.resolveTransition) {
        active.resolveTransition({
          status: "interrupted",
          reason: options.reason,
        });
        active.resolveTransition = null;
      }

      this.stopMotionQueue(options.reason);
      if (options.resetParameters) {
        this.transitionTo("resetting", options.reason);
        this.restoreBaseline(options.reason);
      }

      debug("motion cancelled", {
        reason: options.reason,
        activeMotion: active
          ? {
              token: active.token,
              group: active.group,
              index: active.index,
              queueHandle: active.queueHandle,
            }
          : null,
      });
      this.activeSpecialMotion = null;
      this.baseline = null;

      if (options.startIdle && this.model) {
        this.model.startRandomMotion(IDLE_GROUP, MOTION_PRIORITY.IDLE);
        this.transitionTo("idle", options.reason);
        debug("idle started", { reason: options.reason });
      }
    }

    startAndWaitForMotion(group, index, token) {
      const motionManager = this.model && this.model._motionManager;
      if (!motionManager || !motionManager.isFinishedByHandle) {
        return Promise.resolve({
          status: "failed",
          error: new Error("Cubism motion queue manager is unavailable"),
        });
      }

      const requestTime = performance.now();
      const queueHandle = this.model.startMotion(
        group,
        index,
        MOTION_PRIORITY.SPECIAL,
        undefined,
      );
      if (queueHandle === INVALID_MOTION_HANDLE) {
        return Promise.resolve({
          status: "failed",
          error: new Error(`Unable to start motion ${group}_${index}`),
        });
      }

      const active = this.activeSpecialMotion;
      active.queueHandle = queueHandle;
      active.requestTime = requestTime;
      active.expectedDurationMs = this.motionDurationMs(group, index);
      active.minimumDisplayDurationMs = SPECIAL_MOTION_DISPLAY_MS[group] ||
        active.expectedDurationMs ||
        0;
      debug("motion requested", {
        group,
        index,
        token,
        queueHandle,
        priority: MOTION_PRIORITY.SPECIAL,
        requestTime,
        expectedDurationMs: active.expectedDurationMs,
        minimumDisplayDurationMs: active.minimumDisplayDurationMs,
        state: this.state,
      });

      return new Promise((resolve) => {
        active.resolveCompletion = resolve;

        const pollQueueEntry = () => {
          if (token !== this.motionToken || this.activeSpecialMotion !== active) {
            resolve({ status: "cancelled" });
            return;
          }

          const entry = motionManager.getCubismMotionQueueEntry
            ? motionManager.getCubismMotionQueueEntry(queueHandle)
            : null;
          if (entry && entry.isStarted && entry.isStarted() && !active.startedAt) {
            active.startedAt = performance.now();
            debug("motion actually started", {
              group,
              index,
              token,
              queueHandle,
              startedAt: active.startedAt,
            });
          }

          const queueFinished = motionManager.isFinishedByHandle(queueHandle);
          const finishedAt = performance.now();
          const startedAt = active.startedAt || requestTime;
          const elapsedMs = finishedAt - startedAt;
          if (queueFinished && elapsedMs < active.minimumDisplayDurationMs) {
            if (!active.completionHold && active.startedAt) {
              active.completionHold = this.captureBaseline();
              debug("motion completed before minimum display duration", {
                group,
                index,
                token,
                queueHandle,
                elapsedMs,
                minimumDisplayDurationMs: active.minimumDisplayDurationMs,
              });
            }
            if (active.completionHold) {
              this.applySnapshot(active.completionHold);
            }
          }

          if (
            queueFinished &&
            elapsedMs >= active.minimumDisplayDurationMs
          ) {
            active.animationFrame = null;
            active.resolveCompletion = null;
            debug("motion naturally finished", {
              group,
              index,
              token,
              queueHandle,
              finishedAt,
              elapsedMs,
              expectedDurationMs: active.expectedDurationMs,
              minimumDisplayDurationMs: active.minimumDisplayDurationMs,
              source: "CubismMotionQueueManager.isFinishedByHandle",
            });
            resolve({ status: "completed", elapsedMs });
            return;
          }

          active.animationFrame = window.requestAnimationFrame(pollQueueEntry);
        };

        active.animationFrame = window.requestAnimationFrame(pollQueueEntry);
      });
    }

    async playSpecialMotion(group, index) {
      if (!SPECIAL_MOTION_GROUPS.has(group) || !this.model || !this.model._modelSetting) {
        return;
      }

      const motionCount = this.model._modelSetting.getMotionCount(group);
      const selectedIndex = Number.isInteger(index)
        ? index
        : Math.floor(Math.random() * motionCount);
      if (motionCount <= 0 || selectedIndex < 0 || selectedIndex >= motionCount) {
        debug("invalid special motion", { group, index: selectedIndex });
        return;
      }

      if (this.activeSpecialMotion) {
        debug("new motion supersedes active motion", {
          previous: this.describeActiveMotion(),
          next: { group, index: selectedIndex },
        });
      }
      this.cancelActiveSpecialMotion({
        reason: `superseded by ${group}_${selectedIndex}`,
        resetParameters: true,
        startIdle: false,
      });

      this.baseline = this.captureBaseline();
      this.stopMotionQueue(`starting ${group}_${selectedIndex}`);
      const token = ++this.motionToken;
      this.activeSpecialMotion = {
        token,
        group,
        index: selectedIndex,
        queueHandle: null,
        expectedDurationMs: null,
        minimumDisplayDurationMs: SPECIAL_MOTION_DISPLAY_MS[group] || 0,
        requestTime: null,
        startedAt: null,
        animationFrame: null,
        resolveCompletion: null,
        resolveTransition: null,
        completionHold: null,
      };
      this.transitionTo("special-motion", `starting ${group}_${selectedIndex}`);

      const result = await this.startAndWaitForMotion(group, selectedIndex, token);
      if (
        token !== this.motionToken ||
        !this.activeSpecialMotion ||
        this.activeSpecialMotion.token !== token
      ) {
        return;
      }

      const active = this.activeSpecialMotion;
      if (result.status !== "completed") {
        this.cancelActiveSpecialMotion({
          reason: `motion ${group}_${selectedIndex} ${result.status}`,
          resetParameters: true,
          startIdle: true,
        });
        return;
      }

      this.transitionTo("resetting", `motion ${group}_${selectedIndex} completed`);
      debug("reset requested", {
        reason: "natural motion completion",
        elapsedMs: result.elapsedMs,
        expectedDurationMs: active.expectedDurationMs,
        activeMotion: {
          token: active.token,
          group: active.group,
          index: active.index,
          queueHandle: active.queueHandle,
        },
      });
      this.stopMotionQueue("begin smooth Idle transition");
      const transitionResult = await this.fadeToBaseline(
        active,
        "natural motion completion",
      );
      if (
        transitionResult.status !== "completed" ||
        token !== this.motionToken ||
        this.activeSpecialMotion !== active
      ) {
        return;
      }

      this.activeSpecialMotion = null;
      this.model.setExpression(NEUTRAL_EXPRESSION);
      this.model.startRandomMotion(IDLE_GROUP, MOTION_PRIORITY.IDLE);
      this.baseline = null;
      this.transitionTo("idle", "natural motion completion");
      debug("idle started", { reason: "natural motion completion" });
    }

    destroy(reason) {
      if (this.model && this.originalStartTapMotion) {
        this.cancelActiveSpecialMotion({
          reason,
          resetParameters: false,
          startIdle: false,
        });
        this.model.startTapMotion = this.originalStartTapMotion;
      }
      this.model = null;
      this.originalStartTapMotion = null;
      this.transitionTo("idle", reason);
    }
  }

  const controller = new AvatarMotionController();
  window.xiaohudieAvatarMotionController = controller;

  function attachCurrentModel() {
    const adapter = window.getLAppAdapter && window.getLAppAdapter();
    const model = adapter && adapter.getModel && adapter.getModel();
    controller.attach(model);
  }

  window.setInterval(attachCurrentModel, 250);
  window.addEventListener("DOMContentLoaded", attachCurrentModel);
  window.addEventListener("beforeunload", function () {
    controller.destroy("page unload");
  });
})();
