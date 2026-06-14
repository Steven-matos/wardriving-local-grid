# Rarity, Run Cards, And Signal Heatmap Design

## Goal

Add three dashboard features to the existing WDGWars Local Grid ops console: a rarity score, compact run cards, and a signal heatmap layer.

## Approved Direction

Keep all three features inside the current live ops dashboard rather than adding a separate analytics page. This preserves the map-first Mr. Robot / CyberPunk / Tron / Bladerunner console feel and avoids making the user leave the tactical view.

## Feature Design

### Rarity Score

The importer will calculate a dataset-level `rarity_score` and expose a short list of `rare_signals`. Rarity is based on traits that make an observation interesting inside the local dataset:

- uncommon authentication families, especially WEP, WPA3, Open, and hidden SSIDs
- unusual or sparse channels within the imported run
- strong RSSI observations that are easier to revisit
- low-observation signals that appear only once or twice
- Flock and Bluetooth/BLE tags as special signal types

The dashboard will show rarity as a compact score panel near the existing score, plus a rare-signal list in the right-side analysis area.

### Run Cards

The importer will group data by `capture_date` from the manifest. Each run card will show the date, file count, AP count, observation count, Bluetooth count, Flock count, route miles, rarity score, and dominant file categories.

Cards will be compact and scrollable so they do not compete with the map. They will live in the right-side scroll column.

### Signal Heatmap

The importer will export `heatmap.points` as `[lat, lon, intensity]` entries. Intensity will be derived from RSSI, observations, and special signal tags.

The dashboard will add a `Signal heatmap` toggle to Layer Control. If Leaflet.heat loads, it will render a real heat layer. If the plugin is unavailable, the app will fall back to translucent circle overlays so the layer still works.

## Data Flow

`scripts/import_wardrive.py` remains the data source of truth. It will add:

- `summary.rarity_score`
- `analytics.rare_signals`
- `runs`
- `heatmap.points`

`dashboard/app.js` will read those fields and render them. Missing fields will default gracefully so older generated JSON does not break the dashboard.

## Error Handling

If heatmap data is empty, the layer toggle will remain harmless and no overlay will render. If Leaflet.heat fails to load from CDN, the fallback renderer will draw weighted circle markers.

## Verification

Run the importer with `--skip-import`, serve the dashboard, reload the browser, and verify:

- rarity score appears and updates from data
- run cards render without clipping
- heatmap toggle adds and removes the layer
- existing AP, Bluetooth, Flock, route, POI, upload, duplicate cleanup, and replay controls still work
