#!/usr/bin/env python3
"""
Import, organize, and summarize ESP32 Marauder / WDGWars wardriving files.

Default behavior copies files from a source into data/raw, dedupes by SHA-256,
and regenerates dashboard/data/wardrive-data.json.
Use --move when organizing loose files already in this workspace.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DUPE_DIR = DATA_DIR / "duplicates"
PROCESSED_DIR = DATA_DIR / "processed"
DASHBOARD_DATA_DIR = ROOT / "dashboard" / "data"
MANIFEST_PATH = DATA_DIR / "manifest.json"
DASHBOARD_JSON = DASHBOARD_DATA_DIR / "wardrive-data.json"

MANAGED_DIRS = {
    ".git",
    ".superpowers",
    "dashboard",
    "data",
    "inbox",
    "scripts",
    "SCRIPTS",
}
SUPPORTED_EXTS = {".log", ".gpx", ".pcap", ".pcapng", ".cap", ".csv", ".json", ".bin"}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_read_text(path: Path, limit: int | None = None) -> str:
    data = path.read_bytes()
    if limit is not None:
        data = data[:limit]
    return data.decode("utf-8-sig", errors="replace")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(safe_read_text(MANIFEST_PATH))
    return {"version": 1, "files": []}


def save_manifest(manifest: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest["updated_at"] = now_iso()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def classify_file(path: Path) -> str:
    name = path.name.lower()
    ext = path.suffix.lower()
    if ext == ".bin" or name == "update.bin":
        return "firmware"
    if ext in {".pcap", ".pcapng", ".cap"}:
        return "pcaps"
    if ext == ".gpx":
        if "poi" in name:
            return "pois"
        if "track" in name or "tracker" in name:
            return "tracks"
        return "gpx"
    if ext in {".json"} or name.startswith("aps_"):
        return "aps"
    if "airtag" in name:
        return "airtags"
    if "ssid" in name:
        return "ssids"
    if "ping" in name or "telnet" in name or "scan" in name:
        return "scans"
    if "wardrive" in name or ext == ".csv":
        return "wardrive"
    return "misc"


def parse_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    value = value.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
    ]
    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(value, fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc)
        except ValueError:
            pass
    return None


def detect_capture_date(path: Path, category: str) -> str:
    text = ""
    try:
        text = safe_read_text(path, limit=128 * 1024)
    except OSError:
        pass

    if category == "wardrive":
        for line in text.splitlines():
            if re.match(r"^[0-9A-Fa-f:]{17},", line):
                parts = next(csv.reader([line]))
                if len(parts) >= 4:
                    parsed = parse_datetime(parts[3])
                    if parsed:
                        return parsed.date().isoformat()

    if category in {"tracks", "pois", "gpx"}:
        match = re.search(r"<time>([^<]+)</time>", text)
        parsed = parse_datetime(match.group(1)) if match else None
        if parsed:
            return parsed.date().isoformat()

    try:
        mtime = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
        if mtime.year > 2000:
            return mtime.date().isoformat()
    except OSError:
        pass
    return "undated"


def iter_candidate_files(source: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(source).parts
        if rel_parts and rel_parts[0] in MANAGED_DIRS:
            continue
        if path.suffix.lower() in SUPPORTED_EXTS:
            candidates.append(path)
    return sorted(candidates)


def unique_dest(dest_dir: Path, original: Path, sha: str) -> Path:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", original.stem).strip("._") or "capture"
    suffix = original.suffix.lower()
    return dest_dir / f"{stem}-{sha[:8]}{suffix}"


def next_available(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find an available destination for {path}")


def import_files(source: Path, move: bool) -> dict:
    manifest = load_manifest()
    seen_hashes = {entry["sha256"] for entry in manifest.get("files", [])}
    imported = 0
    skipped = 0
    moved = 0

    for src in iter_candidate_files(source):
        sha = file_sha256(src)
        if sha in seen_hashes:
            skipped += 1
            if move:
                category = classify_file(src)
                capture_date = detect_capture_date(src, category)
                dupe_dir = DUPE_DIR / capture_date / category
                dupe_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(next_available(unique_dest(dupe_dir, src, sha))))
                moved += 1
            continue

        category = classify_file(src)
        capture_date = detect_capture_date(src, category)
        dest_dir = RAW_DIR / capture_date / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = next_available(unique_dest(dest_dir, src, sha))

        if move:
            shutil.move(str(src), str(dest))
            moved += 1
        else:
            shutil.copy2(src, dest)

        manifest.setdefault("files", []).append(
            {
                "sha256": sha,
                "source_name": src.name,
                "source_path": str(src),
                "stored_path": str(dest.relative_to(ROOT)),
                "category": category,
                "capture_date": capture_date,
                "size_bytes": dest.stat().st_size,
                "imported_at": now_iso(),
            }
        )
        seen_hashes.add(sha)
        imported += 1

    save_manifest(manifest)
    return {"imported": imported, "skipped_duplicates": skipped, "moved": moved}


def raw_file_metadata(path: Path) -> tuple[str, str]:
    try:
        rel = path.relative_to(RAW_DIR)
        if len(rel.parts) >= 2:
            return rel.parts[1], rel.parts[0]
    except ValueError:
        pass
    category = classify_file(path)
    return category, detect_capture_date(path, category)


def quarantine_duplicate(path: Path, category: str, capture_date: str, sha: str) -> Path:
    dupe_dir = DUPE_DIR / capture_date / category
    dupe_dir.mkdir(parents=True, exist_ok=True)
    dest = next_available(unique_dest(dupe_dir, path, sha))
    shutil.move(str(path), str(dest))
    return dest


def clean_duplicates() -> dict:
    manifest = load_manifest()
    kept_entries = []
    seen_hashes: dict[str, dict] = {}
    kept_paths: set[Path] = set()
    missing_manifest_files = 0
    hash_repairs = 0
    quarantined_manifest_duplicates = 0
    quarantined_orphan_duplicates = 0
    adopted_orphans = 0

    for entry in manifest.get("files", []):
        stored_path = entry.get("stored_path")
        if not stored_path:
            missing_manifest_files += 1
            continue
        path = ROOT / stored_path
        if not path.exists():
            missing_manifest_files += 1
            continue

        actual_sha = file_sha256(path)
        if actual_sha != entry.get("sha256"):
            entry["sha256"] = actual_sha
            entry["size_bytes"] = path.stat().st_size
            hash_repairs += 1

        category = entry.get("category") or classify_file(path)
        capture_date = entry.get("capture_date") or detect_capture_date(path, category)
        entry["category"] = category
        entry["capture_date"] = capture_date

        if actual_sha in seen_hashes:
            quarantine_duplicate(path, category, capture_date, actual_sha)
            quarantined_manifest_duplicates += 1
            continue

        seen_hashes[actual_sha] = entry
        kept_entries.append(entry)
        kept_paths.add(path.resolve())

    if RAW_DIR.exists():
        for path in sorted(RAW_DIR.rglob("*")):
            if not path.is_file() or path.resolve() in kept_paths:
                continue
            sha = file_sha256(path)
            category, capture_date = raw_file_metadata(path)
            if sha in seen_hashes:
                quarantine_duplicate(path, category, capture_date, sha)
                quarantined_orphan_duplicates += 1
                continue

            entry = {
                "sha256": sha,
                "source_name": path.name,
                "source_path": str(path),
                "stored_path": str(path.relative_to(ROOT)),
                "category": category,
                "capture_date": capture_date,
                "size_bytes": path.stat().st_size,
                "imported_at": now_iso(),
            }
            seen_hashes[sha] = entry
            kept_entries.append(entry)
            kept_paths.add(path.resolve())
            adopted_orphans += 1

    manifest["files"] = kept_entries
    save_manifest(manifest)
    return {
        "hash_repairs": hash_repairs,
        "missing_manifest_files": missing_manifest_files,
        "quarantined_manifest_duplicates": quarantined_manifest_duplicates,
        "quarantined_orphan_duplicates": quarantined_orphan_duplicates,
        "adopted_orphans": adopted_orphans,
        "canonical_files": len(kept_entries),
    }


def parse_float(value: str | int | float | None) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_int(value: str | int | float | None) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def auth_family(auth: str) -> str:
    upper = (auth or "unknown").upper()
    if "WPA3" in upper:
        return "WPA3"
    if "WPA2" in upper:
        return "WPA2"
    if "WPA" in upper:
        return "WPA"
    if "WEP" in upper:
        return "WEP"
    if "OPEN" in upper or upper in {"", "[]"}:
        return "Open"
    return "Other"


def is_flock_signal(row: dict) -> bool:
    haystack = " ".join(
        str(row.get(key, ""))
        for key in ("ssid", "bssid", "auth", "source_file")
    ).lower()
    return "flock" in haystack


def is_bluetooth_signal(row: dict) -> bool:
    haystack = " ".join(
        str(row.get(key, ""))
        for key in ("type", "auth", "ssid", "source_file")
    ).lower()
    return any(token in haystack for token in ("ble", "bluetooth", "btle"))


def parse_wigle(path: Path) -> list[dict]:
    text = safe_read_text(path)
    lines = [line for line in text.splitlines() if line.strip()]
    header_index = next((i for i, line in enumerate(lines) if line.startswith("MAC,SSID,")), None)
    if header_index is None:
        return []

    reader = csv.DictReader(lines[header_index:])
    rows = []
    for row in reader:
        lat = parse_float(row.get("CurrentLatitude"))
        lon = parse_float(row.get("CurrentLongitude"))
        if lat is None or lon is None or lat == 0 or lon == 0:
            continue
        parsed = {
            "bssid": (row.get("MAC") or "").upper(),
            "ssid": row.get("SSID") or "(hidden)",
            "auth": row.get("AuthMode") or "unknown",
            "auth_family": auth_family(row.get("AuthMode") or ""),
            "first_seen": row.get("FirstSeen") or "",
            "channel": parse_int(row.get("Channel")),
            "rssi": parse_int(row.get("RSSI")),
            "lat": lat,
            "lon": lon,
            "altitude": parse_float(row.get("AltitudeMeters")),
            "accuracy": parse_float(row.get("AccuracyMeters")),
            "type": row.get("Type") or "WIFI",
            "source_file": path.name,
        }
        parsed["signal_tags"] = []
        if is_flock_signal(parsed):
            parsed["signal_tags"].append("flock")
        if is_bluetooth_signal(parsed):
            parsed["signal_tags"].append("bluetooth")
        rows.append(parsed)
    return rows


def gpx_namespace(root: ET.Element) -> dict:
    if root.tag.startswith("{"):
        return {"g": root.tag.split("}", 1)[0].strip("{")}
    return {"g": ""}


def child_text(parent: ET.Element, ns: dict, tag: str) -> str:
    if ns["g"]:
        found = parent.find(f"g:{tag}", ns)
    else:
        found = parent.find(tag)
    return found.text.strip() if found is not None and found.text else ""


def parse_gpx(path: Path) -> tuple[list[dict], list[dict]]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return [], []
    ns = gpx_namespace(root)
    prefix = "g:" if ns["g"] else ""
    tracks: list[dict] = []
    pois: list[dict] = []

    for trkseg in root.findall(f".//{prefix}trkseg", ns):
        points = []
        for trkpt in trkseg.findall(f"{prefix}trkpt", ns):
            lat = parse_float(trkpt.attrib.get("lat"))
            lon = parse_float(trkpt.attrib.get("lon"))
            if lat is None or lon is None:
                continue
            points.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "time": child_text(trkpt, ns, "time"),
                    "ele": parse_float(child_text(trkpt, ns, "ele")),
                }
            )
        if points:
            tracks.append({"source_file": path.name, "points": points})

    for wpt in root.findall(f".//{prefix}wpt", ns):
        lat = parse_float(wpt.attrib.get("lat"))
        lon = parse_float(wpt.attrib.get("lon"))
        if lat is None or lon is None:
            continue
        pois.append(
            {
                "lat": lat,
                "lon": lon,
                "name": child_text(wpt, ns, "name") or "POI",
                "time": child_text(wpt, ns, "time"),
                "source_file": path.name,
            }
        )
    return tracks, pois


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    radius = 3958.7613
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def observed_route_miles(rows: list[dict]) -> float:
    seen = set()
    timed_rows = []
    for row in rows:
        stamp = parse_datetime(row.get("first_seen"))
        if stamp is None or row.get("lat") is None or row.get("lon") is None:
            continue
        key = (stamp.isoformat(), round(row["lat"], 5), round(row["lon"], 5))
        if key in seen:
            continue
        seen.add(key)
        timed_rows.append((stamp, row))
    timed_rows.sort(key=lambda item: item[0])

    miles = 0.0
    previous: tuple[float, float] | None = None
    for _stamp, row in timed_rows:
        current = (row["lat"], row["lon"])
        if previous is not None:
            step = haversine_miles(previous, current)
            if step <= 0.2:
                miles += step
        previous = current
    return miles


def replay_kind(row: dict) -> str:
    tags = row.get("signal_tags", [])
    if "flock" in tags:
        return "flock"
    if "bluetooth" in tags:
        return "bluetooth"
    return "wifi"


def clamp(value: float, floor: float, ceiling: float) -> float:
    return max(floor, min(ceiling, value))


def rarity_reasons(item: dict, channel_counts: Counter, auth_counts: Counter) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    auth = item.get("auth_family") or "Other"
    channel = item.get("channel")
    observations = item.get("observations", 1)
    rssi = item.get("rssi")
    tags = item.get("signal_tags", [])

    auth_weights = {
        "WEP": (28, "legacy WEP"),
        "WPA3": (18, "WPA3"),
        "Open": (16, "open net"),
        "WPA": (8, "WPA"),
        "Other": (10, "unusual auth"),
    }
    if auth in auth_weights:
        weight, reason = auth_weights[auth]
        score += weight
        reasons.append(reason)

    if item.get("ssid") == "(hidden)":
        score += 12
        reasons.append("hidden SSID")

    if channel is not None and auth != "bluetooth":
        channel_count = channel_counts.get(str(channel), 0)
        if channel_count <= 3:
            score += 16
            reasons.append(f"sparse ch {channel}")
        elif channel_count <= 10:
            score += 8
            reasons.append(f"low ch {channel}")

    if observations <= 1:
        score += 14
        reasons.append("single hit")
    elif observations <= 3:
        score += 7
        reasons.append("low repeat")

    if rssi is not None:
        if rssi >= -50:
            score += 10
            reasons.append("strong RSSI")
        elif rssi >= -65:
            score += 5
            reasons.append("solid RSSI")

    if "flock" in tags:
        score += 35
        reasons.append("flock tag")
    if "bluetooth" in tags:
        score += 18
        reasons.append("bluetooth")

    auth_count = auth_counts.get(auth, 0)
    if auth_count and auth_count <= 3 and auth not in {"WEP", "WPA3", "Open"}:
        score += 6
        reasons.append("rare auth")

    return int(clamp(score, 0, 100)), reasons[:4]


def heatmap_intensity(item: dict) -> float:
    rssi = item.get("rssi")
    observations = item.get("observations", 1)
    tags = item.get("signal_tags", [])
    if rssi is None:
        base = 0.34
    else:
        base = (clamp(rssi, -95, -35) + 95) / 60
    base += min(0.22, math.log10(max(observations, 1)) * 0.16)
    if "flock" in tags:
        base += 0.22
    if "bluetooth" in tags:
        base += 0.1
    return round(clamp(base, 0.12, 1), 3)


def signal_label(item: dict) -> str:
    ssid = item.get("ssid") or "(hidden)"
    if ssid == "(hidden)":
        return item.get("bssid") or "(hidden)"
    return ssid


def build_rare_signals(items: list[dict], channel_counts: Counter, auth_counts: Counter) -> list[dict]:
    rare = []
    for item in items:
        score, reasons = rarity_reasons(item, channel_counts, auth_counts)
        if score < 18:
            continue
        rare.append(
            {
                "label": signal_label(item),
                "kind": replay_kind(item),
                "score": score,
                "reasons": reasons,
                "rssi": item.get("rssi"),
                "channel": item.get("channel"),
                "observations": item.get("observations", 1),
                "source_file": item.get("source_file", ""),
                "lat": item.get("lat"),
                "lon": item.get("lon"),
            }
        )
    rare.sort(key=lambda item: (-item["score"], item["label"]))
    return rare[:12]


def rarity_summary_score(rare_signals: list[dict]) -> int:
    if not rare_signals:
        return 0
    top = rare_signals[: min(10, len(rare_signals))]
    return round(sum(item["score"] for item in top) / len(top))


def build_run_cards(
    manifest: dict,
    rows: list[dict],
    tracks: list[dict],
    source_dates: dict[str, str],
    channel_counts: Counter,
    auth_counts: Counter,
) -> list[dict]:
    runs: dict[str, dict] = {}
    for entry in manifest.get("files", []):
        run_date = entry.get("capture_date") or "undated"
        run = runs.setdefault(
            run_date,
            {
                "date": run_date,
                "files": 0,
                "categories": Counter(),
                "observations": 0,
                "unique_aps": set(),
                "bluetooth_signals": set(),
                "flock_signals": set(),
                "route_miles": 0.0,
                "rarity_scores": [],
                "first_seen": "",
                "last_seen": "",
            },
        )
        run["files"] += 1
        run["categories"][entry.get("category", "misc")] += 1

    for row in rows:
        run_date = source_dates.get(row.get("source_file", ""), "undated")
        run = runs.setdefault(
            run_date,
            {
                "date": run_date,
                "files": 0,
                "categories": Counter(),
                "observations": 0,
                "unique_aps": set(),
                "bluetooth_signals": set(),
                "flock_signals": set(),
                "route_miles": 0.0,
                "rarity_scores": [],
                "first_seen": "",
                "last_seen": "",
            },
        )
        key = row.get("bssid") or f'{row.get("ssid")}|{row.get("lat")}|{row.get("lon")}'
        if "bluetooth" in row.get("signal_tags", []):
            run["bluetooth_signals"].add(key)
        else:
            run["unique_aps"].add(key)
        if "flock" in row.get("signal_tags", []):
            run["flock_signals"].add(key)
        score, _reasons = rarity_reasons(row, channel_counts, auth_counts)
        run["rarity_scores"].append(score)
        run["observations"] += 1
        seen = row.get("first_seen", "")
        if seen:
            run["first_seen"] = min(filter(None, [run["first_seen"], seen])) if run["first_seen"] else seen
            run["last_seen"] = max(run["last_seen"], seen)

    for track in tracks:
        run_date = source_dates.get(track.get("source_file", ""), "undated")
        run = runs.get(run_date)
        if run is None:
            continue
        for left, right in zip(track["points"], track["points"][1:]):
            run["route_miles"] += haversine_miles((left["lat"], left["lon"]), (right["lat"], right["lon"]))

    cards = []
    for run in runs.values():
        top_scores = sorted(run["rarity_scores"], reverse=True)[:10]
        cards.append(
            {
                "date": run["date"],
                "files": run["files"],
                "categories": dict(run["categories"].most_common(4)),
                "observations": run["observations"],
                "unique_aps": len(run["unique_aps"]),
                "bluetooth_signals": len(run["bluetooth_signals"]),
                "flock_signals": len(run["flock_signals"]),
                "route_miles": round(run["route_miles"], 2),
                "rarity_score": round(sum(top_scores) / len(top_scores)) if top_scores else 0,
                "first_seen": run["first_seen"],
                "last_seen": run["last_seen"],
            }
        )
    cards.sort(key=lambda item: item["date"], reverse=True)
    cards.sort(key=lambda item: item["date"] == "undated")
    return cards[:16]


def build_replay_events(rows: list[dict]) -> list[dict]:
    events = []
    for row in rows:
        stamp = parse_datetime(row.get("first_seen"))
        if stamp is None or row.get("lat") is None or row.get("lon") is None:
            continue
        events.append(
            {
                "time": stamp.isoformat().replace("+00:00", "Z"),
                "epoch": int(stamp.timestamp()),
                "kind": replay_kind(row),
                "lat": row["lat"],
                "lon": row["lon"],
                "bssid": row.get("bssid", ""),
                "ssid": row.get("ssid", "(hidden)"),
                "rssi": row.get("rssi"),
                "channel": row.get("channel"),
                "source_file": row.get("source_file", ""),
            }
        )
    events.sort(key=lambda event: event["epoch"])
    return events


def build_dashboard_data() -> dict:
    manifest = load_manifest()
    wardrive_rows: list[dict] = []
    tracks: list[dict] = []
    pois: list[dict] = []
    source_dates: dict[str, str] = {}

    for entry in manifest.get("files", []):
        path = ROOT / entry["stored_path"]
        if not path.exists():
            continue
        source_dates[path.name] = entry.get("capture_date", "undated")
        if entry["category"] == "wardrive":
            wardrive_rows.extend(parse_wigle(path))
        elif entry["category"] in {"tracks", "pois", "gpx"}:
            parsed_tracks, parsed_pois = parse_gpx(path)
            tracks.extend(parsed_tracks)
            pois.extend(parsed_pois)

    unique_aps: dict[str, dict] = {}
    unique_bluetooth: dict[str, dict] = {}
    observations_by_day = Counter()
    channel_counts = Counter()
    auth_counts = Counter()
    rssi_total = 0
    rssi_count = 0

    for row in wardrive_rows:
        is_bluetooth = "bluetooth" in row.get("signal_tags", [])
        target = unique_bluetooth if is_bluetooth else unique_aps
        key = row["bssid"] or f'{row["ssid"]}|{row["lat"]}|{row["lon"]}'
        existing = target.get(key)
        if existing is None or (row.get("rssi") or -999) > (existing.get("rssi") or -999):
            target[key] = {**row, "observations": 0}
        target[key]["observations"] += 1
        if row.get("first_seen"):
            observations_by_day[row["first_seen"][:10]] += 1
        if row.get("channel") is not None and not is_bluetooth:
            channel_counts[str(row["channel"])] += 1
        if not is_bluetooth:
            auth_counts[row["auth_family"]] += 1
        if row.get("rssi") is not None:
            rssi_total += row["rssi"]
            rssi_count += 1

    for item in [*unique_aps.values(), *unique_bluetooth.values()]:
        rarity_score, reasons = rarity_reasons(item, channel_counts, auth_counts)
        item["rarity_score"] = rarity_score
        item["rarity_reasons"] = reasons
        item["heatmap_intensity"] = heatmap_intensity(item)

    route_miles = 0.0
    route_features = []
    for track in tracks:
        coords = [[point["lon"], point["lat"]] for point in track["points"]]
        for left, right in zip(track["points"], track["points"][1:]):
            route_miles += haversine_miles((left["lat"], left["lon"]), (right["lat"], right["lon"]))
        route_features.append(
            {
                "type": "Feature",
                "properties": {
                    "source_file": track["source_file"],
                    "points": len(track["points"]),
                    "start": track["points"][0].get("time", ""),
                    "end": track["points"][-1].get("time", ""),
                },
                "geometry": {"type": "LineString", "coordinates": coords},
            }
        )

    ap_features = [
        {
            "type": "Feature",
            "properties": {
                "bssid": ap["bssid"],
                "ssid": ap["ssid"],
                "auth": ap["auth"],
                "auth_family": ap["auth_family"],
                "first_seen": ap["first_seen"],
                "channel": ap["channel"],
                "rssi": ap["rssi"],
                "observations": ap["observations"],
                "rarity_score": ap.get("rarity_score", 0),
                "rarity_reasons": ap.get("rarity_reasons", []),
                "heatmap_intensity": ap.get("heatmap_intensity", 0.2),
                "source_file": ap["source_file"],
                "type": ap.get("type", "WIFI"),
                "signal_tags": ap.get("signal_tags", []),
                "is_flock": "flock" in ap.get("signal_tags", []),
                "is_bluetooth": False,
            },
            "geometry": {"type": "Point", "coordinates": [ap["lon"], ap["lat"]]},
        }
        for ap in unique_aps.values()
    ]
    bluetooth_features = [
        {
            "type": "Feature",
            "properties": {
                "bssid": item["bssid"],
                "ssid": item["ssid"],
                "auth": item["auth"],
                "first_seen": item["first_seen"],
                "rssi": item["rssi"],
                "observations": item["observations"],
                "rarity_score": item.get("rarity_score", 0),
                "rarity_reasons": item.get("rarity_reasons", []),
                "heatmap_intensity": item.get("heatmap_intensity", 0.2),
                "source_file": item["source_file"],
                "auth_family": item.get("auth_family", "Other"),
                "type": item.get("type", "BLE"),
                "signal_tags": item.get("signal_tags", []),
                "is_bluetooth": True,
            },
            "geometry": {"type": "Point", "coordinates": [item["lon"], item["lat"]]},
        }
        for item in unique_bluetooth.values()
    ]
    flock_features = [
        feature
        for feature in ap_features
        if feature["properties"].get("is_flock")
    ]

    poi_features = [
        {
            "type": "Feature",
            "properties": {
                "name": poi["name"],
                "time": poi["time"],
                "source_file": poi["source_file"],
            },
            "geometry": {"type": "Point", "coordinates": [poi["lon"], poi["lat"]]},
        }
        for poi in pois
    ]

    display_route_miles = route_miles if route_miles >= 0.1 else observed_route_miles(wardrive_rows)
    replay_events = build_replay_events(wardrive_rows)
    file_counts = Counter(entry["category"] for entry in manifest.get("files", []))
    all_unique_signals = [*unique_aps.values(), *unique_bluetooth.values()]
    rare_signals = build_rare_signals(all_unique_signals, channel_counts, auth_counts)
    rarity_score = rarity_summary_score(rare_signals)
    runs = build_run_cards(manifest, wardrive_rows, tracks, source_dates, channel_counts, auth_counts)
    heatmap_points = [
        [item["lat"], item["lon"], item.get("heatmap_intensity", 0.2)]
        for item in all_unique_signals
        if item.get("lat") is not None and item.get("lon") is not None
    ]
    score = len(unique_aps) * 10 + round(display_route_miles * 25) + len(pois) * 5
    payload = {
        "generated_at": now_iso(),
        "summary": {
            "score": score,
            "rarity_score": rarity_score,
            "unique_aps": len(unique_aps),
            "observations": len(wardrive_rows),
            "bluetooth_signals": len(unique_bluetooth),
            "bluetooth_observations": sum(item["observations"] for item in unique_bluetooth.values()),
            "open_networks": auth_counts["Open"],
            "flock_signals": len(flock_features),
            "hidden_ssids": sum(1 for ap in unique_aps.values() if ap["ssid"] == "(hidden)"),
            "route_miles": round(display_route_miles, 2),
            "gpx_route_miles": round(route_miles, 2),
            "route_points": sum(len(track["points"]) for track in tracks),
            "pois": len(pois),
            "files": len(manifest.get("files", [])),
            "avg_rssi": round(rssi_total / rssi_count, 1) if rssi_count else None,
        },
        "charts": {
            "auth": dict(auth_counts.most_common()),
            "channels": dict(sorted(channel_counts.items(), key=lambda item: int(item[0]))),
            "observations_by_day": dict(sorted(observations_by_day.items())),
            "files": dict(file_counts.most_common()),
        },
        "analytics": {
            "rare_signals": rare_signals,
        },
        "runs": runs,
        "heatmap": {
            "points": heatmap_points,
            "max": 1,
        },
        "features": {"type": "FeatureCollection", "features": ap_features},
        "bluetooth": {"type": "FeatureCollection", "features": bluetooth_features},
        "flock": {"type": "FeatureCollection", "features": flock_features},
        "routes": {"type": "FeatureCollection", "features": route_features},
        "pois": {"type": "FeatureCollection", "features": poi_features},
        "replay": {
            "events": replay_events,
            "start": replay_events[0]["time"] if replay_events else "",
            "end": replay_events[-1]["time"] if replay_events else "",
        },
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.joinpath("wardrive-data.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    DASHBOARD_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Import and organize wardriving files.")
    parser.add_argument("--source", default=str(ROOT), help="Folder or SD card root to import from.")
    parser.add_argument("--move", action="store_true", help="Move files instead of copying them.")
    parser.add_argument("--skip-import", action="store_true", help="Only rebuild dashboard data.")
    parser.add_argument("--clean-duplicates", action="store_true", help="Quarantine duplicate raw files and repair the manifest.")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.exists() or not source.is_dir():
        print(f"Source folder does not exist: {source}", file=sys.stderr)
        return 2

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DATA_DIR.mkdir(parents=True, exist_ok=True)

    result = {"imported": 0, "skipped_duplicates": 0, "moved": 0}
    if not args.skip_import:
        result = import_files(source, move=args.move)
    duplicate_cleanup = None
    if args.clean_duplicates:
        duplicate_cleanup = clean_duplicates()
    payload = build_dashboard_data()

    print(
        json.dumps(
            {
                **result,
                "dashboard_data": str(DASHBOARD_JSON.relative_to(ROOT)),
                "unique_aps": payload["summary"]["unique_aps"],
                "route_miles": payload["summary"]["route_miles"],
                "duplicate_cleanup": duplicate_cleanup,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
