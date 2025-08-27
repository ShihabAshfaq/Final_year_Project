from __future__ import annotations
import os
import threading
import time
import random
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from flask import Flask, jsonify, render_template, request
from flask_sqlalchemy import SQLAlchemy

# -----------------------------
# Flask & DB Setup
# -----------------------------
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///uv_dashboard.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# -----------------------------
# DB Models
# -----------------------------
class SensorReading(db.Model):
    __tablename__ = "sensor_readings"
    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, index=True, nullable=False)
    temperature_c = db.Column(db.Float, nullable=False)
    humidity_pct = db.Column(db.Float, nullable=False)
    uv_index = db.Column(db.Float, nullable=False)
    battery_pct = db.Column(db.Float, nullable=False)

class ActuatorState(db.Model):
    __tablename__ = "actuator_states"
    id = db.Column(db.Integer, primary_key=True)
    # name in {"humidifier","dehumidifier","heater","cooler"}
    name = db.Column(db.String(32), unique=True, nullable=False)
    on = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, nullable=False)

class SystemConfig(db.Model):
    __tablename__ = "system_config"
    id = db.Column(db.Integer, primary_key=True)
    mode = db.Column(db.String(16), nullable=False, default="auto")  # "auto" or "manual"
    target_temperature_c = db.Column(db.Float, nullable=False, default=26.0)
    target_humidity_pct = db.Column(db.Float, nullable=False, default=55.0)

def get_or_create_config() -> SystemConfig:
    cfg = SystemConfig.query.first()
    if not cfg:
        cfg = SystemConfig(mode="auto", target_temperature_c=26.0, target_humidity_pct=55.0)
        db.session.add(cfg)
        db.session.commit()
    return cfg

def ensure_actuators():
    now = datetime.now(timezone.utc)
    for name in ["humidifier","dehumidifier","heater","cooler"]:
        row = ActuatorState.query.filter_by(name=name).one_or_none()
        if not row:
            db.session.add(ActuatorState(name=name, on=False, updated_at=now))
    db.session.commit()

# -----------------------------
# Simulation
# -----------------------------
_sim_thread = None
_stop_flag = False

def simulate_reading(prev: Dict[str, float] | None) -> Dict[str, float]:
    """Return a new 'reading' based on previous values (random walk)."""
    if prev is None:
        prev = {
            "temperature_c": 25.0 + random.uniform(-1, 1),
            "humidity_pct": 50.0 + random.uniform(-5, 5),
            "uv_index": 3.0 + random.uniform(-1, 1),
            "battery_pct": 100.0,
        }
    else:
        # small drift + noise
        prev["temperature_c"] += random.uniform(-0.15, 0.15)
        prev["humidity_pct"] += random.uniform(-0.8, 0.8)
        prev["uv_index"] += random.uniform(-0.2, 0.2)
        # battery drains slowly
        prev["battery_pct"] -= random.uniform(0.001, 0.02)
        # clamp sensible ranges
        prev["temperature_c"] = max(18.0, min(prev["temperature_c"], 40.0))
        prev["humidity_pct"] = max(20.0, min(prev["humidity_pct"], 90.0))
        prev["uv_index"] = max(0.0, min(prev["uv_index"], 12.0))
        prev["battery_pct"] = max(0.0, min(prev["battery_pct"], 100.0))
    return prev

def auto_control(reading: Dict[str, float], cfg: SystemConfig):
    """Simple hysteresis-based automatic control for actuators."""
    # thresholds
    t_lo = cfg.target_temperature_c - 0.8
    t_hi = cfg.target_temperature_c + 0.8
    h_lo = cfg.target_humidity_pct - 3
    h_hi = cfg.target_humidity_pct + 3

    heater = ActuatorState.query.filter_by(name="heater").one()
    cooler = ActuatorState.query.filter_by(name="cooler").one()
    humidifier = ActuatorState.query.filter_by(name="humidifier").one()
    dehumidifier = ActuatorState.query.filter_by(name="dehumidifier").one()

    now = datetime.now(timezone.utc)

    # Temperature control
    if reading["temperature_c"] < t_lo:
        if not heater.on:
            heater.on = True; heater.updated_at = now
        if cooler.on:
            cooler.on = False; cooler.updated_at = now
    elif reading["temperature_c"] > t_hi:
        if not cooler.on:
            cooler.on = True; cooler.updated_at = now
        if heater.on:
            heater.on = False; heater.updated_at = now
    else:
        # in band -> turn both off
        if heater.on:
            heater.on = False; heater.updated_at = now
        if cooler.on:
            cooler.on = False; cooler.updated_at = now

    # Humidity control
    if reading["humidity_pct"] < h_lo:
        if not humidifier.on:
            humidifier.on = True; humidifier.updated_at = now
        if dehumidifier.on:
            dehumidifier.on = False; dehumidifier.updated_at = now
    elif reading["humidity_pct"] > h_hi:
        if not dehumidifier.on:
            dehumidifier.on = True; dehumidifier.updated_at = now
        if humidifier.on:
            humidifier.on = False; humidifier.updated_at = now
    else:
        if humidifier.on:
            humidifier.on = False; humidifier.updated_at = now
        if dehumidifier.on:
            dehumidifier.on = False; dehumidifier.updated_at = now

    db.session.commit()

def _sim_loop():
    """Background simulator: every second, write a reading and auto-control if needed."""
    prev = None
    while not _stop_flag:
        time.sleep(1.0)
        cfg = get_or_create_config()
        data = simulate_reading(prev)
        prev = data.copy()
        # Insert reading
        row = SensorReading(
            ts=datetime.now(timezone.utc),
            temperature_c=float(data["temperature_c"]),
            humidity_pct=float(data["humidity_pct"]),
            uv_index=float(data["uv_index"]),
            battery_pct=float(data["battery_pct"]),
        )
        db.session.add(row)
        db.session.commit()

        if cfg.mode == "auto":
            auto_control(data, cfg)

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/state")
def api_state():
    # latest reading
    r = SensorReading.query.order_by(SensorReading.ts.desc()).first()
    if not r:
        # return default until data arrives
        reading = dict(temperature_c=None, humidity_pct=None, uv_index=None, battery_pct=None, ts=None)
    else:
        reading = dict(
            temperature_c=r.temperature_c,
            humidity_pct=r.humidity_pct,
            uv_index=r.uv_index,
            battery_pct=r.battery_pct,
            ts=r.ts.isoformat(),
        )

    # actuators
    actuators = {}
    for name in ["humidifier","dehumidifier","heater","cooler"]:
        row = ActuatorState.query.filter_by(name=name).one_or_none()
        actuators[name] = dict(on=row.on, updated_at=row.updated_at.isoformat()) if row else dict(on=False, updated_at=None)

    cfg = get_or_create_config()
    return jsonify(dict(
        reading=reading,
        actuators=actuators,
        mode=cfg.mode,
        targets=dict(temperature_c=cfg.target_temperature_c, humidity_pct=cfg.target_humidity_pct),
        server_time=datetime.now(timezone.utc).isoformat(),
    ))

@app.route("/api/history")
def api_history():
    try:
        minutes = int(request.args.get("minutes", "60"))
    except ValueError:
        minutes = 60
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    rows = (SensorReading.query
            .filter(SensorReading.ts >= cutoff)
            .order_by(SensorReading.ts.asc())
            .all())
    data = [dict(
        ts=r.ts.isoformat(),
        temperature_c=r.temperature_c,
        humidity_pct=r.humidity_pct,
        uv_index=r.uv_index,
        battery_pct=r.battery_pct,
    ) for r in rows]
    return jsonify(dict(minutes=minutes, readings=data))

@app.route("/api/actuators/<name>/toggle", methods=["POST"])
def api_toggle(name: str):
    name = name.lower()
    if name not in {"humidifier","dehumidifier","heater","cooler"}:
        return jsonify({"error":"unknown actuator"}), 400
    body = request.get_json(force=True, silent=True) or {}
    on = bool(body.get("on", False))

    cfg = get_or_create_config()
    if cfg.mode != "manual":
        return jsonify({"error":"switch to manual mode to toggle actuators"}), 400

    row = ActuatorState.query.filter_by(name=name).one()
    row.on = on
    row.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"ok": True, "name": name, "on": row.on})

@app.route("/api/mode", methods=["POST"])
def api_mode():
    body = request.get_json(force=True, silent=True) or {}
    mode = str(body.get("mode","")).lower()
    if mode not in {"auto","manual"}:
        return jsonify({"error":"mode must be 'auto' or 'manual'"}), 400
    cfg = get_or_create_config()
    cfg.mode = mode
    db.session.commit()
    return jsonify({"ok": True, "mode": cfg.mode})

@app.route("/api/targets", methods=["POST"])
def api_targets():
    body = request.get_json(force=True, silent=True) or {}
    try:
        t = float(body.get("temperature"))
        h = float(body.get("humidity"))
    except (TypeError, ValueError):
        return jsonify({"error":"temperature & humidity must be numbers"}), 400
    cfg = get_or_create_config()
    cfg.target_temperature_c = max(15.0, min(t, 45.0))
    cfg.target_humidity_pct = max(10.0, min(h, 95.0))
    db.session.commit()
    return jsonify({"ok": True, "targets": {
        "temperature_c": cfg.target_temperature_c, "humidity_pct": cfg.target_humidity_pct
    }})

def _start_sim():
    global _sim_thread
    if _sim_thread and _sim_thread.is_alive():
        return
    # ensure DB baseline
    with app.app_context():
        db.create_all()
        ensure_actuators()
    # start thread
    def runner():
        with app.app_context():
            _sim_loop()
    _sim_thread = threading.Thread(target=runner, daemon=True)
    _sim_thread.start()

@app.before_request
def _ensure_running():
    # lazily start simulation on first request
    if not hasattr(app, "_sim_started"):
        _start_sim()
        app._sim_started = True

if __name__ == "__main__":
    print("Starting UV Testbed Dashboard (Simulation) on http://127.0.0.1:5000")
    _start_sim()
    app.run(debug=True)
