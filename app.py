import os
import csv
import io
import json
import math
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI, Header, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
DB_PATH = os.getenv("AIRSHIELD_DB_PATH", str(APP_DIR / "airshield.db"))
DEVICE_TOKEN = os.getenv("DEVICE_TOKEN", "")
app = FastAPI(title="AirShield AI", version="1.0.0")


def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp_utc TEXT NOT NULL,
                device_id TEXT NOT NULL,
                pm25_ugm3 REAL NOT NULL,
                temperature_c REAL,
                humidity_pct REAL,
                source_type TEXT NOT NULL DEFAULT 'sensor',
                quality_flag TEXT NOT NULL DEFAULT 'valid',
                intervention TEXT NOT NULL DEFAULT 'baseline'
            )
        """)
        conn.commit()


init_db()


class Reading(BaseModel):
    timestamp_utc: Optional[datetime] = None
    device_id: str = Field(default="indoor_01", max_length=80)
    pm25_ugm3: float = Field(ge=0, le=5000)
    temperature_c: Optional[float] = Field(default=None, ge=-30, le=80)
    humidity_pct: Optional[float] = Field(default=None, ge=0, le=100)
    source_type: str = Field(default="sensor", max_length=30)
    quality_flag: str = Field(default="valid", max_length=30)
    intervention: str = Field(default="baseline", max_length=50)


class ScenarioRequest(BaseModel):
    current_pm25: float = Field(ge=0, le=5000)
    outdoor_pm25: Optional[float] = Field(default=None, ge=0, le=5000)
    duration_minutes: int = Field(default=30, ge=5, le=240)
    filtration_strength: float = Field(default=0.5, ge=0, le=1)
    ventilation_strength: float = Field(default=0.3, ge=0, le=1)


def save_reading(r: Reading):
    ts = r.timestamp_utc or datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    with db() as conn:
        conn.execute("""
            INSERT INTO readings
            (timestamp_utc, device_id, pm25_ugm3, temperature_c, humidity_pct,
             source_type, quality_flag, intervention)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts.astimezone(timezone.utc).isoformat(), r.device_id, r.pm25_ugm3,
            r.temperature_c, r.humidity_pct, r.source_type, r.quality_flag,
            r.intervention
        ))
        conn.commit()


def get_readings(limit=1000, device_id=None):
    with db() as conn:
        if device_id:
            rows = conn.execute(
                "SELECT * FROM readings WHERE device_id=? ORDER BY id DESC LIMIT ?",
                (device_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM readings ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in reversed(rows)]


@app.get("/", response_class=HTMLResponse)
def home():
    return (APP_DIR / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"status": "ok", "service": "AirShield AI"}


@app.post("/api/readings")
def create_reading(reading: Reading, x_device_token: Optional[str] = Header(default=None)):
    if DEVICE_TOKEN and x_device_token != DEVICE_TOKEN:
        raise HTTPException(status_code=401, detail="Missing or invalid X-Device-Token")
    save_reading(reading)
    return {"ok": True, "saved": True}


@app.get("/api/readings")
def list_readings(limit: int = 300, device_id: Optional[str] = None):
    limit = max(1, min(limit, 5000))
    return {"readings": get_readings(limit=limit, device_id=device_id)}


@app.get("/api/summary")
def summary():
    rows = get_readings(limit=1000)
    if not rows:
        return {"count": 0, "latest": None, "mean_pm25": None, "freshness_seconds": None}
    latest = rows[-1]
    ts = datetime.fromisoformat(latest["timestamp_utc"].replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = max(0, (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds())
    valid = [r["pm25_ugm3"] for r in rows if r["quality_flag"] == "valid"]
    return {
        "count": len(rows),
        "latest": latest,
        "mean_pm25": round(sum(valid) / len(valid), 2) if valid else None,
        "freshness_seconds": round(age, 1),
        "data_status": "fresh" if age <= 180 else "stale"
    }


@app.get("/api/forecast")
def forecast():
    rows = [r for r in get_readings(limit=1000) if r["quality_flag"] == "valid"]
    if len(rows) < 5:
        return {
            "ready": False,
            "message": "Need at least 5 valid readings. Forecast is not available yet.",
            "baseline": None, "ml_estimate": None, "model": "not enough data"
        }
    values = np.array([r["pm25_ugm3"] for r in rows], dtype=float)
    baseline = float(values[-1])
    # Small-data-safe trend estimate; this is deliberately labelled a prototype model.
    window = values[-min(10, len(values)):]
    x = np.arange(len(window), dtype=float)
    slope = float(np.polyfit(x, window, 1)[0]) if len(window) >= 3 else 0.0
    estimate = max(0.0, baseline + slope)
    variability = float(np.std(np.diff(window))) if len(window) >= 3 else 0.0
    return {
        "ready": True,
        "horizon_minutes": 1,
        "baseline": round(baseline, 2),
        "ml_estimate": round(estimate, 2),
        "model": "short-window linear trend prototype",
        "uncertainty_band": [
            round(max(0, estimate - 1.96 * variability), 2),
            round(estimate + 1.96 * variability, 2)
        ],
        "n_readings": len(rows),
        "warning": "Prototype estimate, not a validated health or safety forecast."
    }


@app.post("/api/scenarios")
def scenarios(req: ScenarioRequest):
    # Transparent, hypothetical first-order model. Parameters are assumptions, not learned facts.
    # Filtration_strength and ventilation_strength represent user-entered normalized assumptions.
    minutes = req.duration_minutes
    indoor = req.current_pm25
    outdoor = req.outdoor_pm25
    filtration_rate = 0.015 * req.filtration_strength
    ventilation_rate = 0.02 * req.ventilation_strength
    scenarios_out = []

    def simulate(label, filt, vent):
        k = 0.015 * filt + 0.02 * vent
        eq = outdoor if outdoor is not None else indoor
        predicted = eq + (indoor - eq) * math.exp(-k * minutes)
        return {
            "name": label,
            "predicted_pm25": round(max(0, predicted), 2),
            "assumption": f"Illustrative first-order model; k={k:.4f}/min",
            "simulated_only": True
        }

    scenarios_out.append({
        "name": "No change",
        "predicted_pm25": round(indoor, 2),
        "assumption": "Concentration held constant as a comparison baseline",
        "simulated_only": True
    })
    scenarios_out.append(simulate("Filtration scenario", req.filtration_strength, 0))
    scenarios_out.append(simulate("Ventilation scenario", 0, req.ventilation_strength))
    scenarios_out.append(simulate("Combined scenario", req.filtration_strength, req.ventilation_strength))
    scenarios_out.sort(key=lambda x: x["predicted_pm25"])
    return {
        "duration_minutes": minutes,
        "scenarios": scenarios_out,
        "warning": "These are hypothetical scenarios, not measured intervention effects. Validate in an unoccupied room before drawing conclusions."
    }


@app.post("/api/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file")
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        inserted = 0
        for row in reader:
            pm = row.get("pm25_ugm3") or row.get("pm25") or row.get("pm25_concentration")
            if pm is None or pm.strip() == "":
                continue
            ts = row.get("timestamp_utc") or row.get("timestamp") or row.get("datetime")
            try:
                timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else datetime.now(timezone.utc)
            except ValueError:
                continue
            reading = Reading(
                timestamp_utc=timestamp,
                device_id=row.get("device_id") or "csv_import",
                pm25_ugm3=float(pm),
                temperature_c=float(row["temperature_c"]) if row.get("temperature_c") else None,
                humidity_pct=float(row["humidity_pct"]) if row.get("humidity_pct") else None,
                source_type="public",
                quality_flag="valid",
                intervention=row.get("intervention") or "baseline"
            )
            save_reading(reading)
            inserted += 1
        return {"ok": True, "inserted": inserted}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}")


@app.get("/api/export.csv")
def export_csv():
    rows = get_readings(limit=5000)
    out = io.StringIO()
    fields = ["timestamp_utc", "device_id", "pm25_ugm3", "temperature_c",
              "humidity_pct", "source_type", "quality_flag", "intervention"]
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    writer.writerows([{k: r.get(k) for k in fields} for r in rows])
    from fastapi.responses import Response
    return Response(content=out.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=airshield-readings.csv"})
