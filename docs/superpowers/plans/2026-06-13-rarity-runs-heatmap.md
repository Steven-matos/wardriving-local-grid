# Rarity, Run Cards, And Signal Heatmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add rarity scoring, run cards, and a weighted signal heatmap to the existing local wardriving dashboard.

**Architecture:** Extend the Python importer to publish analytics fields in `wardrive-data.json`, then render those fields in the existing single-page dashboard. Keep the current map-first layout and add controls inside the existing HUD panels.

**Tech Stack:** Python standard library, static HTML/CSS/JavaScript, Leaflet, optional Leaflet.heat CDN plugin with JavaScript fallback rendering.

---

### Task 1: Extend Dashboard Data

**Files:**
- Modify: `scripts/import_wardrive.py`

- [ ] Add helper functions for rarity scoring, run grouping, and heatmap intensity.
- [ ] Add `summary.rarity_score`, `analytics.rare_signals`, `runs`, and `heatmap.points` to the generated payload.
- [ ] Run `python .\scripts\import_wardrive.py --skip-import` and confirm `dashboard/data/wardrive-data.json` is regenerated locally.

### Task 2: Add Dashboard Markup

**Files:**
- Modify: `dashboard/index.html`

- [ ] Add a rarity score panel near the existing score.
- [ ] Add a `Signal heatmap` button to Layer Control.
- [ ] Add right-side panels for `Run Cards` and `Rare Signals`.
- [ ] Add the Leaflet.heat script after Leaflet.

### Task 3: Render New UI And Layer

**Files:**
- Modify: `dashboard/app.js`

- [ ] Add heatmap layer state and toggle support.
- [ ] Render heatmap via `L.heatLayer` when available.
- [ ] Render fallback circle overlays when `L.heatLayer` is unavailable.
- [ ] Render run cards and rare-signal rows from generated analytics.
- [ ] Update the import feed with rarity and run counts.

### Task 4: Style The New Panels

**Files:**
- Modify: `dashboard/styles.css`

- [ ] Style rarity score, run cards, rare-signal rows, and heatmap toggle states.
- [ ] Keep panels compact and scroll-safe inside the existing HUD layout.
- [ ] Verify mobile layout still stacks without overlap.

### Task 5: Verify And Publish

**Files:**
- Modify if needed: `README.md`

- [ ] Run `python .\scripts\import_wardrive.py --skip-import`.
- [ ] Start or reuse `python .\scripts\serve_dashboard.py`.
- [ ] Reload `http://localhost:8080` and verify the new features visually.
- [ ] Confirm Git still ignores `data/` and `dashboard/data/wardrive-data.json`.
- [ ] Commit and push only code/docs changes.
