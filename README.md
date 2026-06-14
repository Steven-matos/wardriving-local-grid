# WarDriving Local Grid

Local WDGWars-inspired dashboard and importer for ESP32 Marauder wardriving files.

## Use The Dashboard

1. Import or refresh data:

   ```powershell
   python .\scripts\import_wardrive.py --skip-import
   ```

2. Serve the dashboard:

   ```powershell
   python .\scripts\serve_dashboard.py
   ```

3. Open `http://localhost:8080`.

The dashboard includes an `Upload Captures` panel. Select or drop a batch of `.log`, `.gpx`, `.pcap`, `.csv`, `.json`, or `.bin` files and it will import, dedupe, organize, and refresh the map.

Use `Clean Duplicates` in the dashboard to scan `data/raw`, quarantine duplicate files into `data/duplicates`, and prune duplicate manifest entries without deleting captures.

Use `Mission Replay` to animate your observations chronologically across the map. The replay stream includes Wi-Fi, Bluetooth/BLE, and Flock events.

The dashboard also highlights special signal layers:

- Flock signals when an imported observation includes `flock` in the SSID/source metadata.
- Bluetooth/BLE signals when imported Wigle/Marauder rows contain `Type=BLE` or `[BLE]`.

## Import From An SD Card

Copy new files from a card, dedupe them by SHA-256, organize them by capture date and type, and refresh the dashboard data:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\import_sd.ps1 -Source E:\
```

To watch for removable drives and import when one appears:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\watch_sd.ps1
```

The default is copy-only. Add `-Move` only if you want imported files removed from the source card.

To run duplicate cleanup from the terminal:

```powershell
python .\scripts\import_wardrive.py --skip-import --clean-duplicates
```

## Folder Layout

- `data/raw/YYYY-MM-DD/<type>/` stores original captures.
- `data/processed/wardrive-data.json` stores the parsed dashboard payload.
- `dashboard/data/wardrive-data.json` is the copy loaded by the web dashboard.
- `scripts/import_wardrive.py` handles importing, dedupe, parsing, and dashboard generation.
- `scripts/watch_sd.ps1` gives you the plug-in-SD workflow on Windows.

The importer classifies Wigle wardrive logs, GPX tracks, GPX POIs, AP JSON logs, scan logs, PCAPs, firmware files, and miscellaneous supported files.
