(function installAvatarLipSyncController() {
  "use strict";

  const HANDLER_PATCHED = Symbol("avatarLipSyncHandlerPatched");
  const NativeAudio = window.Audio;

  function getCurrentModel() {
    const manager = window.getLive2DManager?.();
    if (manager?.getModel) {
      return manager.getModel(0);
    }
    return window.getLAppAdapter?.()?.getModel?.() || null;
  }

  function closeMouth(model) {
    const coreModel = model?._model;
    const lipSyncIds = model?._lipSyncIds;
    if (!coreModel?.setParameterValueById || !lipSyncIds?.getSize) {
      return;
    }

    for (let index = 0; index < lipSyncIds.getSize(); index += 1) {
      const parameterId = lipSyncIds.at(index);
      if (parameterId) {
        coreModel.setParameterValueById(parameterId, 0);
      }
    }
  }

  function resetModelLipSync(model, releasePcm = true) {
    const handler = model?._wavFileHandler;
    if (handler) {
      if (releasePcm && typeof handler.releasePcmData === "function") {
        handler.releasePcmData();
      }
      handler._lastRms = 0;
      handler._sampleOffset = 0;
      handler._userTimeSeconds = 0;
    }
    closeMouth(model);
  }

  function patchModel(model) {
    const handler = model?._wavFileHandler;
    if (!handler || handler[HANDLER_PATCHED]) {
      return Boolean(handler);
    }

    const originalStart = handler.start.bind(handler);
    const originalUpdate = handler.update.bind(handler);

    handler.start = function startFreshLipSync(audioUrl) {
      resetModelLipSync(model, true);
      return originalStart(audioUrl);
    };

    handler.update = function updateLipSync(deltaTimeSeconds) {
      const hasSamples = originalUpdate(deltaTimeSeconds);
      if (!hasSamples) {
        this._lastRms = 0;
        closeMouth(model);
      }
      return hasSamples;
    };

    handler[HANDLER_PATCHED] = true;
    return true;
  }

  function patchCurrentModel() {
    return patchModel(getCurrentModel());
  }

  if (typeof NativeAudio === "function") {
    function ManagedAudio(...args) {
      const audio = new NativeAudio(...args);
      const finishLipSync = () => resetModelLipSync(getCurrentModel(), true);
      audio.addEventListener("ended", finishLipSync);
      audio.addEventListener("error", finishLipSync);
      audio.addEventListener("abort", finishLipSync);
      return audio;
    }

    ManagedAudio.prototype = NativeAudio.prototype;
    Object.setPrototypeOf(ManagedAudio, NativeAudio);
    window.Audio = ManagedAudio;
  }

  const controller = {
    closeMouth,
    getCurrentModel,
    patchModel,
    patchNow: patchCurrentModel,
    resetModelLipSync,
  };
  window.avatarLipSyncController = controller;

  patchCurrentModel();
  window.setInterval(patchCurrentModel, 250);
  window.addEventListener("load", patchCurrentModel, { once: true });
})();
