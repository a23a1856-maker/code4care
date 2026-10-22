/* CODE4CARE: camera barcode scanning and small form helpers.
   Everything the camera reads goes to the server for validation; nothing is
   stored in the browser beyond the one-time request id. */
(function () {
  "use strict";

  function newRequestId() {
    if (window.crypto && window.crypto.randomUUID) return window.crypto.randomUUID();
    return "r" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  var form = document.getElementById("scan-form");
  var input = document.getElementById("barcode-input");
  var requestId = document.getElementById("request-id");
  var video = document.getElementById("camera");
  var status = document.getElementById("scan-status");
  var startButton = document.getElementById("start-camera");
  var stopButton = document.getElementById("stop-camera");

  var detector = null;
  var stream = null;
  var scanning = false;
  var timer = null;

  function setStatus(text, state) {
    if (!status) return;
    status.textContent = text;
    status.setAttribute("data-status", state || "idle");
  }

  if (form && input && requestId) {
    form.addEventListener("submit", function () {
      requestId.value = newRequestId();
    });
    form.addEventListener("htmx:afterRequest", function () {
      if (scanning) pause();
    });
  }

  function submit(value) {
    if (!form || !input) return;
    input.value = value;
    if (requestId) requestId.value = newRequestId();
    if (window.htmx) {
      window.htmx.trigger(form, "submit");
    } else {
      form.submit();
    }
  }

  function pause() {
    scanning = false;
    if (timer) {
      window.clearTimeout(timer);
      timer = null;
    }
  }

  function stopCamera() {
    pause();
    if (stream) {
      stream.getTracks().forEach(function (track) { track.stop(); });
      stream = null;
    }
    if (video) video.srcObject = null;
    if (startButton) startButton.hidden = false;
    if (stopButton) stopButton.hidden = true;
  }

  function detectLoop() {
    if (!scanning || !detector || !video) return;
    detector
      .detect(video)
      .then(function (codes) {
        if (codes && codes.length > 0) {
          var value = (codes[0].rawValue || "").trim();
          if (value) {
            setStatus("Kod bar dikesan: " + value, "found");
            submit(value);
            return;
          }
        }
      })
      .catch(function () {
        /* a frame that cannot be read is normal; keep scanning */
      })
      .finally(function () {
        if (scanning) timer = window.setTimeout(detectLoop, 400);
      });
  }

  function startCamera() {
    if (!video || !startButton) return;
    if (!("BarcodeDetector" in window) || !navigator.mediaDevices) {
      setStatus(
        "Pelayar ini tidak menyokong imbasan kamera. Taip kod bar secara manual di bawah.",
        "unsupported"
      );
      if (input) input.focus();
      return;
    }
    detector = new window.BarcodeDetector({
      formats: ["ean_13", "ean_8", "upc_a", "code_128", "qr_code"]
    });
    setStatus("Meminta kebenaran kamera\u2026", "starting");
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then(function (mediaStream) {
        stream = mediaStream;
        video.srcObject = mediaStream;
        return video.play();
      })
      .then(function () {
        startButton.hidden = true;
        if (stopButton) stopButton.hidden = false;
        scanning = true;
        setStatus("Halakan kod bar ke dalam bingkai.", "scanning");
        detectLoop();
      })
      .catch(function () {
        setStatus(
          "Kamera tidak dapat digunakan. Benarkan akses kamera atau taip kod bar secara manual.",
          "denied"
        );
        if (input) input.focus();
      });
  }

  if (startButton) startButton.addEventListener("click", startCamera);
  if (stopButton) {
    stopButton.addEventListener("click", function () {
      stopCamera();
      setStatus("Kamera dihentikan.", "idle");
    });
  }
  window.addEventListener("pagehide", stopCamera);

  document.body.addEventListener("htmx:responseError", function (event) {
    if (event.detail && event.detail.xhr && event.detail.xhr.status === 401) {
      window.location.href = "/login";
    }
  });

  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.addEventListener("click", function () {
      window.print();
    });
  });
})();
