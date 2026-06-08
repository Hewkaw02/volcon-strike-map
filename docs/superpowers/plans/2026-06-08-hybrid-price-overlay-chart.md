# Hybrid Price Overlay Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add daily and intraday price charts overlaid with option-derived levels.

**Architecture:** Extend provider adapters to fetch or synthesize price bars. Add chart payloads to updater output, then render an SVG chart in the static frontend with daily/intraday controls. Keep GitHub Pages static and keep tokens in GitHub Actions only.

**Tech Stack:** Python standard library, pytest, vanilla HTML/CSS/JavaScript, GitHub Actions.

---

## Tasks

- [ ] Add failing provider tests for daily history, intraday timesales, and Tradier normalization.
- [ ] Implement `PriceBar` model and provider history methods.
- [ ] Add failing updater test asserting `price_charts.daily` and `price_charts.intraday` exist in public JSON.
- [ ] Implement updater chart payloads and sample fallback charts.
- [ ] Add price overlay chart panel, SVG renderer, and daily/intraday toggle.
- [ ] Update workflow schedule to refresh intraday data during market hours plus after close.
- [ ] Verify pytest, updater output, JS syntax, rendered chart, interaction, live Pages deployment.

