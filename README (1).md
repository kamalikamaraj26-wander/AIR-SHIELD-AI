# AirShield AI

**Evidence-driven clean-air intervention planning for schools.** This hackathon prototype combines PM2.5 sensor readings, optional public historical data, a small short-term trend estimate, and a transparent intervention scenario simulator.

> Safety and science note: forecast and intervention outputs are prototypes, not medical advice or declarations that a room is safe. Scenario outputs are simulated until validated with real measurements.

## Features

- FastAPI application with a lightweight browser dashboard
- POST endpoint for ESP32 or other sensor readings
- SQLite storage and CSV export/import
- Live PM2.5 trend chart and sensor freshness indicator
- Short-window trend estimate, shown only after enough readings
- Transparent filtration/ventilation scenario comparison
- Dockerfile for deployment on AWS App Runner or another container host

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8080
```

Open http://127.0.0.1:8080. Health check: http://127.0.0.1:8080/health.

### Load sample data

Use the **Import CSV** button in the dashboard and select `sample_data.csv`. These are demonstration values, not real environmental observations. The sample timestamps are historical; the UI will correctly mark them stale.

## API examples

Add a reading:

```bash
curl -X POST http://127.0.0.1:8080/api/readings \
  -H "Content-Type: application/json" \
  -d '{"device_id":"indoor_01","pm25_ugm3":12.4,"temperature_c":27.1,"humidity_pct":62,"source_type":"sensor","quality_flag":"valid"}'
```

Readings: `GET /api/readings`

Summary: `GET /api/summary`

Forecast: `GET /api/forecast`

Scenario comparison:

```bash
curl -X POST http://127.0.0.1:8080/api/scenarios \
  -H "Content-Type: application/json" \
  -d '{"current_pm25":35,"outdoor_pm25":20,"duration_minutes":30,"filtration_strength":0.7,"ventilation_strength":0.3}'
```

Export CSV: `GET /api/export.csv`

CSV import accepts columns `timestamp_utc` (or `timestamp` / `datetime`) and `pm25_ugm3` (or `pm25` / `pm25_concentration`). Optional columns: `device_id`, `temperature_c`, `humidity_pct`, `intervention`.

## Connect an ESP32

1. Open `firmware/airshield_esp32.ino`.
2. Set Wi-Fi name/password and the URL of your deployed service.
3. Set `DEVICE_TOKEN` on the server and the same token in firmware if you want authenticated device writes.
4. Confirm your particulate sensor's exact UART pins, baud rate, packet format, supply voltage and wiring from its datasheet. The included firmware uses a Plantower-compatible 32-byte frame parser; adapt it if your sensor differs.
5. Flash firmware. Confirm `POST /api/readings` returns HTTP 200.

**Security:** never commit Wi-Fi credentials or device tokens. Use environment variables/secrets in deployment. For an internet-facing deployment, set `DEVICE_TOKEN` to a long random value. The firmware transmits that token as `X-Device-Token`. Do not share it in screenshots or the public repository.

## Public data

You can download suitable PM2.5 records from [OpenAQ](https://docs.openaq.org/) and import a CSV through the UI. Check station coverage, units, timestamp timezone, license and data quality first. Keep public, sensor and simulated data clearly labelled. Public outdoor data should not be described as indoor measurements.

## Docker

```bash
docker build -t airshield-ai .
docker run --rm -p 8080:8080 -e DEVICE_TOKEN="replace-with-long-random-secret" airshield-ai
```

Open http://localhost:8080.

### AWS App Runner

1. Push this repository to GitHub.
2. In AWS App Runner, create a service from the GitHub repository (or build/push the image and deploy from ECR).
3. Use the included `Dockerfile`.
4. Configure the service port as `8080` (or allow App Runner's `PORT` environment variable).
5. Add `DEVICE_TOKEN` as a secret/environment variable if sensor write authentication is required.
6. Deploy and verify `/health` and the root dashboard.
7. **Storage warning:** this starter uses local SQLite. Container-local storage may not be durable across redeployments and does not provide shared persistence across multiple instances. For a real long-running service, use a managed database or durable storage. For the hackathon demo, export CSV snapshots regularly.

AWS docs: https://docs.aws.amazon.com/apprunner/latest/dg/what-is-apprunner.html

## Research novelty and evaluation

The proposed research question is whether uncertainty-aware intervention selection, updated using sensor feedback, improves recommendation reliability versus a fixed-rule baseline. This repository is a starting prototype, not proof of novelty or efficacy.

For a fair evaluation:
- Compare forecasts with a persistence baseline on a chronological holdout.
- Record observed before/after PM2.5 values for controlled, unoccupied-room tests.
- Keep intervention assumptions, outdoor conditions and sensor placement in the experiment log.
- Report MAE, number of test samples, and uncertainty/abstention cases.
- Do not claim the ML model is better unless the test data supports it.
- Do not deliberately introduce harmful pollutants or expose students to test conditions.

## Limitations

- Trend estimate is a short-window linear trend, not a trained or validated forecasting model.
- Intervention equations are illustrative scenario calculations, not a calibrated indoor-air model.
- The prototype does not calculate official AQI or certify room safety.
- SQLite local storage is suitable for a demo, not multi-instance production persistence.
- Low-cost optical PM sensors can be affected by humidity, aerosol composition and placement.
