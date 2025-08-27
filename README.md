# UV Testbed Dashboard (Simulation)

This is a **Flask-based** dashboard that simulates your project’s real-time environment:
- Live sensor streams: **Temperature (°C), Humidity (%), UV Index, Battery (%)**
- Actuator controls: **Humidifier, Dehumidifier, Heater, Cooler**
- Automatic or manual control modes
- SQLite logging + simple history API
- Clean, professional UI with **Tailwind CSS** and **Chart.js**

> Designed from your Sprint reports to mirror requirements: MQTT-style data relay, real-time dashboard, actuator toggling, SQL logging, Raspberry Pi-friendly stack.

---

## Quick Start

```bash
# 1) Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Run the app
python app.py

# 4) Open the dashboard
# Visit http://127.0.0.1:5000
```

The app starts a background **simulation thread** that produces sensor values every second
and logs them to SQLite (`uv_dashboard.db`).

---

## Project Structure

```
uv_dashboard_sim/
├─ app.py                   # Flask app + background simulator thread
├─ requirements.txt
├─ templates/
│  └─ index.html            # Dashboard page (Tailwind + Chart.js)
├─ static/
│  ├─ js/
│  │  └─ dashboard.js       # Frontend logic: fetch APIs, live update, charts
│  └─ css/
│     └─ styles.css         # Optional overrides
└─ README.md
```

---

## API Overview

- `GET /api/state`
  - Returns latest sensor reading, actuator states, mode, and targets.
- `GET /api/history?minutes=60`
  - Returns time-series readings for the last N minutes (default 60).
- `POST /api/actuators/<name>/toggle` JSON: `{ "on": true/false }`
  - Sets an actuator explicitly (in **manual** mode).
- `POST /api/mode` JSON: `{ "mode": "auto" | "manual" }`
- `POST /api/targets` JSON: `{ "temperature": 26, "humidity": 55 }`

> In **auto** mode, the simulator will switch actuators to keep temperature/humidity near targets.

---

## Notes & Next Steps

- Swap the `simulate_reading()` generator with a real **MQTT** subscriber to connect
  your Raspberry Pi nodes.
- Add authentication if deploying externally.
- Extend the DB schema for per-experiment metadata, user logs, and ML-derived metrics.
