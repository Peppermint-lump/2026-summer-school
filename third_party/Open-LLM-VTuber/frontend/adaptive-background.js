(function () {
  "use strict";

  const DAY_START_HOUR = 6;
  const NIGHT_START_HOUR = 17;
  const DAY_VIDEO = "/bg/xiaohudie-day.mp4";
  const NIGHT_VIDEO = "/bg/xiaohudie-night.mp4";
  const VIDEO_ID = "xiaohudie-adaptive-background";

  function selectedVideoUrl(now) {
    const hour = now.getHours();
    return hour >= DAY_START_HOUR && hour < NIGHT_START_HOUR
      ? DAY_VIDEO
      : NIGHT_VIDEO;
  }

  function installVideo() {
    const image = document.querySelector('img[alt="background"]');
    if (!image || !image.parentElement) {
      return;
    }

    image.style.display = "none";

    let video = document.getElementById(VIDEO_ID);
    if (!video) {
      video = document.createElement("video");
      video.id = VIDEO_ID;
      video.autoplay = true;
      video.loop = true;
      video.muted = true;
      video.playsInline = true;
      video.setAttribute("aria-hidden", "true");
      Object.assign(video.style, {
        position: "absolute",
        inset: "0",
        width: "100%",
        height: "100%",
        objectFit: "cover",
        zIndex: "1",
        pointerEvents: "none",
      });
      image.parentElement.insertBefore(video, image.nextSibling);
    }

    const nextUrl = selectedVideoUrl(new Date());
    if (video.getAttribute("src") !== nextUrl) {
      video.setAttribute("src", nextUrl);
      video.load();
      video.play().catch(function () {
        // Muted autoplay normally succeeds; a later user gesture retries it.
      });
    }
  }

  const observer = new MutationObserver(installVideo);
  observer.observe(document.documentElement, { childList: true, subtree: true });

  window.addEventListener("DOMContentLoaded", installVideo);
  window.addEventListener("pointerdown", installVideo, { passive: true });
  window.setInterval(installVideo, 60 * 1000);
})();
