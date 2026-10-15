(() => {
  const $ = id => document.getElementById(id);
  const video = $("camera");
  let stream = null, modelsReady = false;
  const MODEL_URLS = [
    "https://cdn.jsdelivr.net/gh/vladmandic/face-api@master/model",
    "https://raw.githubusercontent.com/vladmandic/face-api/master/model"
  ];
  function message(text, type="info") {
    const el = $("action-status");
    if (!el) return;
    el.textContent = text; el.className = `alert ${type}`;
  }
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => {
        script.remove();
        reject(new Error("Could not load face library from " + src));
      };
      document.head.appendChild(script);
    });
  }

  async function ensureFaceApi() {
    if (window.faceapi) return;

    // face-api.js 0.22.2 does not expose the expected /build/face-api.js
    // file on the CDNs previously configured. Use the maintained browser bundle.
    const urls = [
      "https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.15/dist/face-api.js",
      "https://unpkg.com/@vladmandic/face-api@1.7.15/dist/face-api.js"
    ];
    let lastError;
    for (const url of urls) {
      try {
        await loadScript(url);
        if (window.faceapi) return;
        lastError = new Error("Script loaded but window.faceapi was not created.");
      } catch (e) {
        lastError = e;
      }
    }
    throw new Error("Face library could not load. Check internet/CDN access. " +
      (lastError?.message || ""));
  }
  async function loadModels() {
    if (modelsReady) return;
    await ensureFaceApi();
    $("face-status").textContent = "Loading face recognition models…";
    let lastError;
    for (const base of MODEL_URLS) {
      try {
        await faceapi.nets.tinyFaceDetector.loadFromUri(base);
        await faceapi.nets.faceLandmark68Net.loadFromUri(base);
        await faceapi.nets.faceRecognitionNet.loadFromUri(base);
        modelsReady = true;
        return;
      } catch (e) { lastError = e; }
    }
    throw new Error("Face library loaded, but model files could not load. Check internet/CDN access. " + (lastError?.message || ""));
  }
  async function descriptor() {
    await loadModels();
    if (!stream || video.readyState < 2) throw new Error("First click Enable camera and wait until your face appears.");
    const result = await faceapi.detectSingleFace(video, new faceapi.TinyFaceDetectorOptions({inputSize:320,scoreThreshold:.5})).withFaceLandmarks().withFaceDescriptor();
    if (!result) throw new Error("No face detected. Look straight at the camera in good lighting.");
    return Array.from(result.descriptor);
  }
  function location() {
    return new Promise((resolve,reject) => {
      if (!navigator.geolocation) return reject(new Error("GPS is not supported by this browser."));
      navigator.geolocation.getCurrentPosition(p => resolve({latitude:p.coords.latitude,longitude:p.coords.longitude,accuracy:p.coords.accuracy}),
        e => reject(new Error(e.code===1 ? "Allow location permission in browser settings." : "Could not get GPS. Turn on location services and retry.")),
        {enableHighAccuracy:true,timeout:20000,maximumAge:0});
    });
  }
  async function previewLocation() {
    try {
      $("location-status").textContent = "Checking device location…";
      const loc = await location();
      $("location-status").textContent = `GPS received (accuracy approx. ${Math.round(loc.accuracy)}m). Server checks office distance.`;
      $("location-indicator").textContent = "Received";
      $("location-indicator").className = "status good";
      return loc;
    } catch (e) { if ($("location-status")) $("location-status").textContent=e.message; throw e; }
  }
  $("start-camera").addEventListener("click", async () => {
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Camera requires HTTPS or localhost.");
      stream = await navigator.mediaDevices.getUserMedia({video:{facingMode:"user",width:{ideal:640},height:{ideal:480}},audio:false});
      video.srcObject = stream;
      await video.play();
      $("camera-placeholder").classList.add("hidden");
      await loadModels();
      $("face-status").textContent = "Camera and face models ready. Click Enroll face.";
      $("start-camera").textContent = "Camera enabled";
      message("Camera is ready. Click Enroll face.", "success");
    } catch(e) { message(e.message,"error"); }
  });
  $("enroll-face").addEventListener("click", async () => {
    try {
      $("enroll-face").disabled = true;
      const d = await descriptor();
      const r = await fetch("/api/face/enroll",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({descriptor:d})});
      const data = await r.json(); if(!r.ok) throw new Error(data.detail || "Enrollment failed.");
      $("face-status").textContent = "Face enrolled successfully.";
      window.ATTENDANCE_CONFIG.hasFace = true; message(data.message || "Face enrollment saved.","success");
    } catch(e) { message(e.message,"error"); }
    finally { if (!window.ATTENDANCE_CONFIG?.hasFace) $("enroll-face").disabled = false; }
  });
  async function act(action) {
    try {
      if (!window.ATTENDANCE_CONFIG.hasFace) throw new Error("Enroll your face first.");
      const loc = await previewLocation(), d = await descriptor();
      const r = await fetch(`/api/attendance/${action}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...loc,descriptor:d})});
      const data = await r.json(); if(!r.ok) throw new Error(data.detail || "Attendance action failed.");
      message(data.message,"success");
      if(data.record) {
        $("check-in-time").textContent=data.record.check_in || "— : —";
        $("check-out-time").textContent=data.record.check_out || "— : —";
      }
      if(action==="check-in") {$("check-in").disabled=true;$("check-out").disabled=false;}
      if(action==="check-out") $("check-out").disabled=true;
    } catch(e) { message(e.message,"error"); }
  }
  [["check-in","check-in"],["check-out","check-out"],["lunch-start","lunch-start"],["lunch-end","lunch-end"]].forEach(([id,action]) => $(id).addEventListener("click",()=>act(action)));
  previewLocation().catch(()=>{});
})();
