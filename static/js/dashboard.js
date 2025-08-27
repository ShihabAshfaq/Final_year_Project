let thChart, ubChart;

let currentTargets = { temperature_c: 26, humidity_pct: 55 };

function fmt(n, digits=1) {
  return (n === null || n === undefined) ? "--" : Number(n).toFixed(digits);
}
function setModeBadge(mode) {
  const badge = document.getElementById("mode-badge");
  badge.textContent = mode;
  badge.className = "ml-2 inline-block text-xs px-2 py-1 rounded " +
    (mode === "auto" ? "bg-blue-100 text-blue-800" : "bg-orange-100 text-orange-800");
}

// --- stats helpers ---
function stats(arr) {
  const clean = arr.filter(v => v !== null && v !== undefined && !Number.isNaN(v));
  if (clean.length === 0) return { avg: null, min: null, max: null };
  const sum = clean.reduce((a,b)=>a+b,0);
  const avg = sum / clean.length;
  const min = Math.min(...clean);
  const max = Math.max(...clean);
  return { avg, min, max, n: clean.length };
}
function pct(n) { return n===null || n===undefined ? '--' : (Math.round(n*1000)/10)+'%'; }
function num(n, d=1){ return (n===null||n===undefined||Number.isNaN(n)) ? '--' : n.toFixed(d); }
function withinBand(arr, target, tol) {
  const clean = arr.filter(v => typeof v==='number' && !Number.isNaN(v));
  if (clean.length===0) return null;
  const ok = clean.filter(v => v>=target-tol && v<=target+tol).length;
  return ok/clean.length;
}
function updateTHStats(temp, hum) {
  const sT = stats(temp), sH = stats(hum);
  document.getElementById('stat-temp-avg').textContent = num(sT.avg, 1) + ' °C';
  document.getElementById('stat-temp-minmax').textContent = num(sT.min,1) + ' / ' + num(sT.max,1);

  document.getElementById('stat-hum-avg').textContent = num(sH.avg, 0) + ' %';
  document.getElementById('stat-hum-minmax').textContent = num(sH.min,0) + ' / ' + num(sH.max,0);

  const tBand = withinBand(temp, currentTargets.temperature_c, 0.8);
  const hBand = withinBand(hum, currentTargets.humidity_pct, 3.0);
  document.getElementById('stat-temp-band').textContent = pct(tBand);
  document.getElementById('stat-hum-band').textContent = pct(hBand);
}
function updateUBStats(uv, batt, xs) {
  const sU = stats(uv), sB = stats(batt);
  document.getElementById('stat-uv-avg').textContent = num(sU.avg,1);
  document.getElementById('stat-uv-max').textContent = num(sU.max,1);

  document.getElementById('stat-batt-avg').textContent = num(sB.avg,0) + ' %';
  document.getElementById('stat-batt-min').textContent = num(sB.min,0) + ' %';

  // linear drain estimate
  let drain = null, eta = null;
  if (batt.length >= 2 && xs.length>=2) {
    const minutes = (xs[xs.length-1] - xs[0]) / 60000.0;
    if (minutes > 0) {
      const delta = batt[batt.length-1] - batt[0]; // typically negative
      const perHour = (delta / minutes) * 60.0;     // % per hour
      drain = perHour;
      if (perHour < 0) eta = batt[batt.length-1] / (-perHour);
    }
  }
  document.getElementById('stat-batt-drain').textContent = (drain===null?'--':num(drain,1)+' %/h');
  document.getElementById('stat-batt-eta').textContent = (eta===null?'--':num(eta,1)+' h');
}

// --- API pulls ---
async function fetchState() {
  const res = await fetch('/api/state');
  const data = await res.json();

  const r = data.reading || {};
  document.getElementById('stat-temp').textContent = fmt(r.temperature_c);
  document.getElementById('stat-hum').textContent = fmt(r.humidity_pct, 0);
  document.getElementById('stat-uv').textContent = fmt(r.uv_index, 1);
  document.getElementById('stat-batt').textContent = fmt(r.battery_pct, 0);
  document.getElementById('server-time').textContent = data.server_time?.replace('T',' ').split('.')[0] || '--';
  document.getElementById('state-ts').textContent = r.ts ? r.ts.replace('T',' ').split('.')[0] : '--';
  document.getElementById('last-updated').textContent = "Updated " + (new Date()).toLocaleTimeString();

  const ring = document.getElementById('batt-ring');
  ring.textContent = fmt(r.battery_pct,0) + "%";

  setModeBadge(data.mode);

  document.getElementById('target-temp').value = data.targets?.temperature_c ?? 26;
  currentTargets.temperature_c = data.targets?.temperature_c ?? 26;

  document.getElementById('target-hum').value = data.targets?.humidity_pct ?? 55;
  currentTargets.humidity_pct = data.targets?.humidity_pct ?? 55;

  document.querySelectorAll('.act-btn').forEach(btn => {
    const name = btn.dataset.act;
    const on = data.actuators?.[name]?.on;
    if (on) {
      btn.classList.add('bg-green-600','text-white');
      btn.classList.remove('bg-gray-100','hover:bg-gray-200');
    } else {
      btn.classList.remove('bg-green-600','text-white');
      btn.classList.add('bg-gray-100','hover:bg-gray-200');
    }
  });
}

async function fetchHistory() {
  const res = await fetch('/api/history?minutes=60');
  const json = await res.json();
  const xs = json.readings.map(r => new Date(r.ts));
  const temp = json.readings.map(r => r.temperature_c);
  const hum = json.readings.map(r => r.humidity_pct);
  const uv = json.readings.map(r => r.uv_index);
  const batt = json.readings.map(r => r.battery_pct);

  if (!thChart) {
    thChart = new Chart(document.getElementById('thChart'), {
      type: 'line',
      data: {
        labels: xs,
        datasets: [
          { label: 'Temperature (°C)', data: temp },
          { label: 'Humidity (%)', data: hum },
        ]
      },
      options: {
        responsive: true,
        animation: false,
        scales: {
          x: { type: 'time', time: { unit: 'minute' } },
          y: { beginAtZero: false }
        }
      }
    });
  } else {
    thChart.data.labels = xs;
    thChart.data.datasets[0].data = temp;
    thChart.data.datasets[1].data = hum;
    thChart.update();
  }

  if (!ubChart) {
    ubChart = new Chart(document.getElementById('ubChart'), {
      type: 'line',
      data: {
        labels: xs,
        datasets: [
          { label: 'UV Index', data: uv },
          { label: 'Battery (%)', data: batt },
        ]
      },
      options: {
        responsive: true,
        animation: false,
        scales: {
          x: { type: 'time', time: { unit: 'minute' } },
          y: { beginAtZero: false }
        }
      }
    });
  } else {
    ubChart.data.labels = xs;
    ubChart.data.datasets[0].data = uv;
    ubChart.data.datasets[1].data = batt;
    ubChart.update();
  }

  // NEW: update stat cards under charts
  updateTHStats(temp, hum);
  updateUBStats(uv, batt, xs);
}

// --- actions ---
async function setMode(mode) {
  const res = await fetch('/api/mode', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ mode })
  });
  const j = await res.json();
  if (!j.ok) alert(j.error || 'Failed to set mode');
  else setModeBadge(j.mode);
}

async function saveTargets() {
  const t = parseFloat(document.getElementById('target-temp').value);
  const h = parseFloat(document.getElementById('target-hum').value);
  const res = await fetch('/api/targets', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ temperature: t, humidity: h })
  });
  const j = await res.json();
  const status = document.getElementById('save-status');
  status.textContent = j.ok ? 'Targets saved.' : (j.error || 'Failed to save.');
  setTimeout(() => status.textContent = '', 2000);
}

async function toggleActuator(name) {
  const res = await fetch('/api/actuators/' + name + '/toggle', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ on: true })
  });
  const j = await res.json();
  if (j.error) alert(j.error);
  fetchState();
}

function wireUp() {
  document.getElementById('btn-auto').addEventListener('click', () => setMode('auto'));
  document.getElementById('btn-manual').addEventListener('click', () => setMode('manual'));
  document.getElementById('save-targets').addEventListener('click', saveTargets);
  document.querySelectorAll('.act-btn').forEach(btn => {
    btn.addEventListener('click', () => toggleActuator(btn.dataset.act));
  });

  fetchState(); fetchHistory();
  setInterval(fetchState, 1500);
  setInterval(fetchHistory, 8000);
}

document.addEventListener('DOMContentLoaded', wireUp);
