const state = {
  layers: {},
  visible: { aps: true, bluetooth: true, flock: true, routes: true, pois: true },
  data: null,
  replay: {
    events: [],
    index: 0,
    timer: null,
    playing: false,
    speed: 20,
    layer: L.layerGroup(),
    path: L.polyline([], { color: "#ffcf5a", weight: 3, opacity: 0.82 }),
  },
};

const map = L.map("map", {
  zoomControl: true,
  preferCanvas: true,
});

L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  attribution: '&copy; OpenStreetMap &copy; CARTO',
  maxZoom: 20,
}).addTo(map);

map.setView([39.5, -98.35], 4);

const colors = {
  Open: "#ff4f6d",
  WEP: "#ffcf5a",
  WPA: "#4ea7ff",
  WPA2: "#58ffea",
  WPA3: "#4dff88",
  Other: "#ff3df2",
};

const replayColors = {
  wifi: "#58ffea",
  bluetooth: "#4ea7ff",
  flock: "#ff3df2",
};

function text(id, value) {
  document.getElementById(id).textContent = value;
}

function number(value) {
  return new Intl.NumberFormat().format(value ?? 0);
}

function makeBars(id, values, maxRows = 12) {
  const container = document.getElementById(id);
  const entries = Object.entries(values || {}).slice(0, maxRows);
  const max = Math.max(...entries.map((entry) => entry[1]), 1);
  container.innerHTML = entries
    .map(([label, count]) => {
      const width = Math.max(3, Math.round((count / max) * 100));
      return `
        <div class="bar-row">
          <span>${label}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
          <strong>${count}</strong>
        </div>
      `;
    })
    .join("");
}

function pointRadius(feature) {
  const rssi = feature.properties.rssi ?? -90;
  if (rssi > -45) return 8;
  if (rssi > -65) return 6;
  return 4;
}

function flockRadius(feature) {
  return Math.max(9, pointRadius(feature) + 4);
}

function bluetoothRadius(feature) {
  return Math.max(5, pointRadius(feature) + 1);
}

function formatReplayTime(value) {
  if (!value) return "--:--:--";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function addLayers(data) {
  Object.values(state.layers).forEach((layer) => layer.removeFrom(map));
  state.layers = {};

  state.layers.routes = L.geoJSON(data.routes, {
    style: () => ({
      color: "#58ffea",
      weight: 4,
      opacity: 0.82,
      dashArray: "8 10",
    }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindPopup(`<strong>${p.source_file}</strong><br>${p.points} GPS points<br>${p.start || ""}`);
    },
  }).addTo(map);

  state.layers.aps = L.geoJSON(data.features, {
    pointToLayer: (feature, latlng) => {
      const family = feature.properties.auth_family || "Other";
      return L.circleMarker(latlng, {
        radius: pointRadius(feature),
        color: colors[family] || colors.Other,
        fillColor: colors[family] || colors.Other,
        fillOpacity: 0.68,
        weight: 1,
      });
    },
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindPopup(`
        <strong>${p.ssid}</strong><br>
        ${p.bssid}<br>
        ${p.auth_family} / ch ${p.channel ?? "n/a"} / ${p.rssi ?? "n/a"} dBm<br>
        ${p.first_seen || ""}<br>
        <small>${p.source_file}</small>
      `);
    },
  }).addTo(map);

  state.layers.bluetooth = L.geoJSON(data.bluetooth, {
    pointToLayer: (feature, latlng) =>
      L.circleMarker(latlng, {
        radius: bluetoothRadius(feature),
        color: "#4ea7ff",
        fillColor: "#58ffea",
        fillOpacity: 0.48,
        weight: 2,
        opacity: 0.95,
        className: "bluetooth-pulse",
      }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindPopup(`
        <strong>Bluetooth signal</strong><br>
        ${p.bssid}<br>
        ${p.type || "BLE"} / ${p.rssi ?? "n/a"} dBm<br>
        ${p.first_seen || ""}<br>
        observations: ${p.observations ?? 1}<br>
        <small>${p.source_file}</small>
      `);
    },
  }).addTo(map);

  state.layers.flock = L.geoJSON(data.flock, {
    pointToLayer: (feature, latlng) =>
      L.circleMarker(latlng, {
        radius: flockRadius(feature),
        color: "#ff3df2",
        fillColor: "#ffcf5a",
        fillOpacity: 0.78,
        weight: 3,
        opacity: 1,
        className: "flock-pulse",
      }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindPopup(`
        <strong>Flock signal</strong><br>
        ${p.ssid} / ${p.bssid}<br>
        ${p.auth_family} / ch ${p.channel ?? "n/a"} / ${p.rssi ?? "n/a"} dBm<br>
        ${p.first_seen || ""}<br>
        <small>${p.source_file}</small>
      `);
    },
  }).addTo(map);

  state.layers.pois = L.geoJSON(data.pois, {
    pointToLayer: (_feature, latlng) =>
      L.circleMarker(latlng, {
        radius: 7,
        color: "#ffcf5a",
        fillColor: "#ffcf5a",
        fillOpacity: 0.9,
        weight: 2,
      }),
    onEachFeature: (feature, layer) => {
      const p = feature.properties;
      layer.bindPopup(`<strong>${p.name}</strong><br>${p.time || ""}<br><small>${p.source_file}</small>`);
    },
  }).addTo(map);

  state.replay.layer.addTo(map);
  state.replay.path.addTo(map);

  const bounds = L.featureGroup(Object.values(state.layers)).getBounds();
  if (bounds.isValid()) {
    map.fitBounds(bounds.pad(0.15));
  }
}

function bindToggles() {
  document.querySelectorAll(".toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.layer;
      state.visible[key] = !state.visible[key];
      button.classList.toggle("active", state.visible[key]);
      if (state.visible[key]) {
        state.layers[key].addTo(map);
      } else {
        state.layers[key].removeFrom(map);
      }
    });
  });
}

function bindUploads() {
  const form = document.getElementById("uploadForm");
  const input = document.getElementById("fileInput");
  const button = document.getElementById("uploadButton");
  const cleanButton = document.getElementById("cleanButton");
  const label = document.getElementById("uploadLabel");
  const status = document.getElementById("uploadStatus");
  const dropzone = document.getElementById("dropzone");

  const setFiles = (files) => {
    if (!files || files.length === 0) {
      label.textContent = "Drop files or select a batch";
      return;
    }
    label.textContent = `${files.length} file${files.length === 1 ? "" : "s"} armed for import`;
  };

  input.addEventListener("change", () => setFiles(input.files));

  ["dragenter", "dragover"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragging");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragging");
    });
  });

  dropzone.addEventListener("drop", (event) => {
    input.files = event.dataTransfer.files;
    setFiles(input.files);
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!input.files || input.files.length === 0) {
      status.textContent = "no files selected";
      return;
    }

    const formData = new FormData();
    Array.from(input.files).forEach((file) => formData.append("files", file, file.name));
    button.disabled = true;
    status.textContent = `uploading ${input.files.length} file${input.files.length === 1 ? "" : "s"}...`;

    try {
      const response = await fetch("/api/upload", { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || `HTTP ${response.status}`);
      }
      status.textContent = `imported ${result.imported}, skipped ${result.skipped_duplicates}, moved ${result.moved}`;
      input.value = "";
      setFiles(input.files);
      await loadData();
    } catch (error) {
      status.textContent = `upload failed: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  });

  cleanButton.addEventListener("click", async () => {
    cleanButton.disabled = true;
    status.textContent = "scanning archive for duplicates...";
    try {
      const response = await fetch("/api/clean-duplicates", { method: "POST" });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || `HTTP ${response.status}`);
      }
      const moved =
        result.quarantined_manifest_duplicates + result.quarantined_orphan_duplicates;
      status.textContent = `cleaned ${moved} duplicate${moved === 1 ? "" : "s"}; ${result.canonical_files} canonical files`;
      await loadData();
    } catch (error) {
      status.textContent = `cleanup failed: ${error.message}`;
    } finally {
      cleanButton.disabled = false;
    }
  });
}

function replayMarker(event) {
  const color = replayColors[event.kind] || replayColors.wifi;
  return L.circleMarker([event.lat, event.lon], {
    radius: event.kind === "flock" ? 9 : event.kind === "bluetooth" ? 6 : 5,
    color,
    fillColor: event.kind === "flock" ? "#ffcf5a" : color,
    fillOpacity: 0.74,
    weight: event.kind === "flock" ? 3 : 2,
    className: "replay-ping",
  });
}

function updateReplayHud(event = null) {
  const total = state.replay.events.length;
  text("replayCount", `${Math.min(state.replay.index, total)} / ${total}`);
  text("replayTime", event ? formatReplayTime(event.time) : "--:--:--");
  text(
    "replaySignal",
    event
      ? `${event.kind.toUpperCase()} ${event.rssi ?? "n/a"} dBm\n${event.ssid || event.bssid}`
      : "standby"
  );
  const slider = document.getElementById("replaySlider");
  slider.max = Math.max(0, total - 1);
  slider.value = Math.min(state.replay.index, Math.max(0, total - 1));
}

function clearReplay() {
  stopReplay();
  state.replay.index = 0;
  state.replay.layer.clearLayers();
  state.replay.path.setLatLngs([]);
  updateReplayHud();
}

function stepReplay(batchSize = state.replay.speed) {
  const events = state.replay.events;
  if (state.replay.index >= events.length) {
    stopReplay();
    return;
  }

  let lastEvent = null;
  const end = Math.min(events.length, state.replay.index + batchSize);
  for (; state.replay.index < end; state.replay.index += 1) {
    const event = events[state.replay.index];
    lastEvent = event;
    replayMarker(event).addTo(state.replay.layer);
    state.replay.path.addLatLng([event.lat, event.lon]);
  }
  updateReplayHud(lastEvent);
}

function playReplay() {
  if (state.replay.playing || state.replay.events.length === 0) return;
  state.replay.playing = true;
  document.getElementById("replayPlay").textContent = "❚❚";
  state.replay.timer = window.setInterval(() => stepReplay(), 90);
}

function stopReplay() {
  state.replay.playing = false;
  if (state.replay.timer) {
    window.clearInterval(state.replay.timer);
    state.replay.timer = null;
  }
  const playButton = document.getElementById("replayPlay");
  if (playButton) playButton.textContent = "▶";
}

function seekReplay(targetIndex) {
  stopReplay();
  state.replay.index = 0;
  state.replay.layer.clearLayers();
  state.replay.path.setLatLngs([]);
  stepReplay(Math.max(0, targetIndex));
}

function bindReplay() {
  const playButton = document.getElementById("replayPlay");
  const resetButton = document.getElementById("replayReset");
  const speed = document.getElementById("replaySpeed");
  const slider = document.getElementById("replaySlider");

  playButton.addEventListener("click", () => {
    if (state.replay.playing) {
      stopReplay();
    } else {
      playReplay();
    }
  });
  resetButton.addEventListener("click", clearReplay);
  speed.addEventListener("change", () => {
    state.replay.speed = Number(speed.value);
  });
  slider.addEventListener("input", () => {
    seekReplay(Number(slider.value));
  });
}

function updateHud(data) {
  state.data = data;
  state.replay.events = data.replay?.events || [];
  clearReplay();
  const s = data.summary;
  text("score", number(s.score));
  text("uniqueAps", number(s.unique_aps));
  text("observations", number(s.observations));
  text("routeMiles", s.route_miles);
  text("pois", number(s.pois));
  text("flockSignals", number(s.flock_signals));
  text("bluetoothSignals", number(s.bluetooth_signals));
  text("openNetworks", number(s.open_networks));
  text("hiddenSsids", number(s.hidden_ssids));
  text("avgRssi", s.avg_rssi === null ? "n/a" : `${s.avg_rssi} dBm`);
  text("fileCount", number(s.files));
  makeBars("authBars", data.charts.auth, 7);
  makeBars("channelBars", data.charts.channels, 14);
  const feed = document.getElementById("feed");
  feed.textContent = [
    `generated ${data.generated_at}`,
    `wifi ${number(s.unique_aps)} | bt ${number(s.bluetooth_signals)} | flock ${number(s.flock_signals)}`,
    `replay ${number(state.replay.events.length)} | gps ${number(s.route_points)} | score ${number(s.score)}`,
    "",
    "upload: use Upload Captures",
    "clean: use Clean Duplicates",
    "",
    "sd import:",
    "powershell -ExecutionPolicy Bypass -File scripts/import_sd.ps1 -Source E:\\",
    "sd watch:",
    "powershell -ExecutionPolicy Bypass -File scripts/watch_sd.ps1",
  ].join("\n");
  feed.scrollTop = 0;
}

async function loadData() {
  const response = await fetch(`./data/wardrive-data.json?t=${Date.now()}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json();
  updateHud(data);
  addLayers(data);
}

loadData()
  .then(() => {
    bindToggles();
    bindUploads();
    bindReplay();
  })
  .catch((error) => {
    text("feed", `dashboard data missing\n${error.message}\n\nRun scripts/import_wardrive.py first.`);
  });
