# AC Drift Tuner

Record your AC drift sessions and let the tuner do the setup work. Reads shared memory, logs to CSV, auto-adjusts pressures, springs, dampers, ARB, diff and camber.

---

## What's Included

| File | What it does |
|---|---|
| `ac_logger.py` | Logs telemetry to CSV while you drive |
| `ac_watcher.py` | Watches for AC to launch and starts the logger automatically |
| `ac_auto_tuner.py` | GUI app — loads your CSV and outputs a tuned setup `.ini` |
| `start_watcher.bat` | Starts the watcher (run this before AC) |
| `start_drift_tuner.bat` | Opens the drift tuner GUI |

---

## Requirements

- Assetto Corsa (Windows)
- Python 3.10+

Install Python via winget if you don't have it:
```
winget install Python.Python.3.12
```

No extra libraries needed — all standard library.

---

## Setup

1. Clone or download this repo
2. Run `start_watcher.bat` before launching AC — it will auto-start logging when you go on track
3. Session CSVs are saved to the `sessions/` folder, named by date, car and track

---

## Auto Tuner

The tuner reads your session CSV and outputs a tuned setup `.ini` file ready to load in AC.

**Before using it:**
1. In Assetto Corsa, load the car you want to tune
2. Set a starting setup
3. Save it as `generic` in the Generic folder — the tuner looks for this file automatically

**Then:**
1. Run `start_drift_tuner.bat`
2. Load your session CSV — the car and base setup are detected automatically
3. Hit **Analyse & Tune**
4. Hit **Save Tuned Setup**

### What gets auto-adjusted

| Parameter | Signal |
|---|---|
| Tyre pressures | Always set to 32 psi front / 20 psi rear |
| Spring rates | Suspension travel avg vs target range |
| Camber | Inner/outer tyre temp spread |
| ARB front/rear | Roll angle and sideslip consistency |
| Rebound dampers | Suspension travel stdev (bounce) |
| Fast rebound | Extreme bounce |
| Fast bump | Peak travel spikes |
| Diff preload | Rear wheel speed difference during drift |
| Diff coast | Oversteer index on lift |
| Brake bias | Front vs rear brake temp ratio |

---

## Telemetry Columns

The logger captures at high frequency:

- Speed, gear, RPM, throttle, brake, steering angle
- Sideslip angle, yaw rate, oversteer index
- Tyre temps — inner, mid and outer per corner
- Working tyre pressures, loads and wear per corner
- Suspension travel and dynamic camber per corner
- Ride height, CG height, turbo boost
- Air temp, road temp, wind speed

---

## Sharing Sessions

Send your CSV to a friend or tuner and they can run it through the auto tuner on their end — no live connection needed. Your friend needs Python installed and the three files: `ac_logger.py`, `ac_watcher.py`, `start_watcher.bat`.

---

## License

MIT — do whatever you want with it.
