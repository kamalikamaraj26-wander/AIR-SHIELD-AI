# Manual smoke tests

1. `GET /health` returns `{"status":"ok","service":"AirShield AI"}`.
2. `POST /api/readings` with a valid JSON reading returns `{"ok":true,"saved":true}`.
3. `GET /api/readings` contains the submitted record.
4. Add at least five valid readings; `GET /api/forecast` returns an estimate labelled as a prototype.
5. `POST /api/scenarios` returns four simulated scenarios and an explicit warning.
6. Upload `sample_data.csv` from the UI and verify that rows are imported and labelled `public`.
7. If `DEVICE_TOKEN` is configured, a POST without the matching `X-Device-Token` returns 401.
8. `GET /api/export.csv` downloads a CSV file.
