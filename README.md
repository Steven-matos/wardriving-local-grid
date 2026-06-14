# WarDriving Local Grid

A local, privacy-first WDGWars-inspired dashboard for visualizing wardriving captures from ESP32 Marauder and similar tooling. It imports capture files, organizes them by type and date, removes duplicates by SHA-256, and renders the results on a cyberpunk map dashboard.

The project is built to keep your raw wardriving data on your machine. The repository contains code only; capture data and generated map payloads are ignored by Git.

## What It Does

- Maps Wi-Fi access point observations with signal, encryption, channel, and hidden-SSID stats.
- Displays Bluetooth/BLE observations when imported rows include BLE metadata.
- Highlights possible Flock-related observations when imported metadata includes `flock`.
- Draws GPX tracks and POIs when they are present in the imported files.
- Provides a mission replay timeline to animate observations chronologically.
- Calculates a local rarity score for unusual signals and high-interest runs.
- Renders run cards grouped by capture date.
- Adds a weighted signal heatmap layer.
- Accepts browser uploads through the dashboard and imports them immediately.
- Watches or imports from an SD card on Windows.
- Deduplicates imported files using SHA-256 hashes so repeated SD-card dumps do not dirty the dataset.

## Requirements

- Windows, macOS, or Linux for the Python dashboard server.
- Python 3.10 or newer.
- PowerShell for the SD-card helper scripts on Windows.
- A modern browser.
- Internet access for the default Leaflet CDN and map tiles.

No Python packages are required beyond the standard library.

## Quick Start

From the project root:

```powershell
python .\scripts\import_wardrive.py --skip-import
python .\scripts\serve_dashboard.py
```

Open:

```text
http://localhost:8080
```

If you already have capture files in another folder or on an SD card, import them first:

```powershell
python .\scripts\import_wardrive.py --source E:\
python .\scripts\serve_dashboard.py
```

## Dashboard Features

The first screen is the operations dashboard. It includes:

- A Leaflet map with access points, Bluetooth/BLE signals, Flock signals, GPX tracks, and POIs.
- Layer controls for turning signal categories on and off.
- A signal heatmap toggle for spotting dense or high-interest zones.
- Channel distribution, signal mix, route miles, AP counts, observation counts, Bluetooth counts, and open/hidden network stats.
- Rarity score, rare-signal list, and run cards for comparing capture sessions.
- Upload Captures for drag-and-drop or file-picker imports.
- Clean Duplicates for one-click duplicate quarantine.
- Import Feed showing the latest local import status and helper commands.
- Mission Replay for watching observations appear over time.

## Supported Files

The importer accepts these extensions:

```text
.log, .gpx, .pcap, .pcapng, .cap, .csv, .json, .bin
```

Files are classified into folders such as:

- `wardrive`
- `tracks`
- `pois`
- `aps`
- `pcaps`
- `firmware`
- `scans`
- `ssids`
- `airtags`
- `misc`

The parser currently understands Wigle-style wardrive rows, GPX tracks, GPX POIs, AP JSON logs, Bluetooth/BLE markers, and basic metadata from other supported capture files.

## Importing Data

### Import From A Folder Or SD Card

Copy files into the local organized data folder:

```powershell
python .\scripts\import_wardrive.py --source E:\
```

By default, imports are copy-only. Add `--move` only when you want the source files removed after import:

```powershell
python .\scripts\import_wardrive.py --source E:\ --move
```

### Import With The Windows SD Helper

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\import_sd.ps1 -Source E:\
```

To move files instead of copying:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\import_sd.ps1 -Source E:\ -Move
```

### Watch For New SD Cards

This watches for removable drives and imports the first time each card appears:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\watch_sd.ps1
```

Optional polling interval:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\watch_sd.ps1 -IntervalSeconds 5
```

### Upload Through The Browser

Start the server:

```powershell
python .\scripts\serve_dashboard.py
```

Then use the Upload Captures panel in the dashboard. Uploaded files are staged under `inbox/uploads/<timestamp>/`, imported, deduplicated, and reflected on the map.

The local upload limit is 512 MB per request.

## Duplicate Handling

Every imported file is hashed with SHA-256. If a file with the same hash has already been imported, the importer skips it instead of adding another copy.

To clean existing duplicates from the organized raw data:

```powershell
python .\scripts\import_wardrive.py --skip-import --clean-duplicates
```

Or press Clean Duplicates in the dashboard.

Duplicate files are moved to:

```text
data/duplicates/
```

The cleanup flow is intentionally conservative: it quarantines duplicate raw files and repairs the manifest instead of deleting captures outright.

## Folder Layout

```text
.
|-- dashboard/
|   |-- index.html
|   |-- styles.css
|   |-- app.js
|   `-- data/
|       `-- wardrive-data.json       # generated locally, not committed
|-- scripts/
|   |-- import_wardrive.py           # import, organize, parse, dedupe, generate dashboard JSON
|   |-- serve_dashboard.py           # local web server and upload API
|   |-- import_sd.ps1                # one-shot SD-card import helper
|   `-- watch_sd.ps1                 # removable-drive watcher
|-- data/
|   |-- raw/                         # original captures, organized by date/type
|   |-- processed/                   # generated processed payloads
|   |-- duplicates/                  # quarantined duplicate captures
|   `-- manifest.json                # local import manifest
`-- inbox/
    `-- uploads/                     # temporary browser upload batches
```

## Privacy And Git Safety

Wardriving data can reveal sensitive location and network metadata. This repo is configured so local captures and generated datasets are not committed.

Ignored by default:

- `data/`
- `inbox/`
- `dashboard/data/wardrive-data.json`
- raw capture extensions such as `.log`, `.gpx`, `.pcap`, `.pcapng`, `.cap`, `.bin`, `.wigle`, `.kismet`, and `.kismetdb`

Before pushing changes, you can verify what Git will include:

```powershell
git status --short --ignored
git diff --cached --name-only
```

If you intentionally add sample data later, sanitize it first and keep it small.

## Server Options

The dashboard server defaults to `0.0.0.0:8080`:

```powershell
python .\scripts\serve_dashboard.py
```

Use another host or port:

```powershell
python .\scripts\serve_dashboard.py --host 127.0.0.1 --port 9090
```

## Troubleshooting

If the map loads but has no points, import or rebuild the generated dashboard data:

```powershell
python .\scripts\import_wardrive.py --skip-import
```

If port 8080 is busy:

```powershell
python .\scripts\serve_dashboard.py --port 9090
```

If the SD-card script is blocked by PowerShell policy, use the included bypass form:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\import_sd.ps1 -Source E:\
```

If duplicate captures keep appearing, run:

```powershell
python .\scripts\import_wardrive.py --skip-import --clean-duplicates
```

## Responsible Use

Use this tool for your own learning, mapping, and capture management. Respect local laws, private property, and network boundaries. This dashboard is for visualizing passive observation data, not for accessing networks you do not own or have permission to test.
