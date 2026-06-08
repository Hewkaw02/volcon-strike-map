# Stock Options VolCon Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a GitHub Pages dashboard that updates daily with nearest-expiry stock option VolCon/CDF/gamma analytics.

**Architecture:** A Python data layer fetches or samples option-chain data through provider adapters, computes derived analytics, and writes public JSON. A static HTML/CSS/JS app renders the JSON as an operational dashboard. GitHub Actions runs the updater daily, commits derived snapshots, and deploys Pages.

**Tech Stack:** Python standard library, pytest, vanilla HTML/CSS/JavaScript, GitHub Actions, GitHub Pages, Tradier API adapter.

---

## File Structure

- `volcon/__init__.py`: package marker and version.
- `volcon/models.py`: dataclasses for quotes, option contracts, strike analytics, ticker analytics, and run output.
- `volcon/calculator.py`: pure analytics functions for expiry selection, forward estimate, CDF, VolCon score, tags, and gamma regime.
- `volcon/providers.py`: provider interface plus sample and Tradier adapters.
- `scripts/update_data.py`: CLI entry point that reads config, builds analytics, writes latest/archive JSON.
- `tests/test_calculator.py`: TDD coverage for nearest expiry, CDF, scoring, tags, and stale-risk metadata.
- `tests/test_providers.py`: TDD coverage for sample provider and Tradier response normalization.
- `config/tickers.json`: default ticker universe and workflow settings.
- `public/index.html`: static dashboard shell.
- `public/styles.css`: dashboard visual system and responsive layout.
- `public/app.js`: fetches `data/latest.json`, renders cards, level map, tables, and risk panels.
- `public/data/latest.json`: committed sample output so Pages renders before secrets exist.
- `.github/workflows/pages.yml`: daily updater and GitHub Pages deployment workflow.
- `README.md`: setup, secrets, methodology, risks, and operating guide.

## Tasks

- [ ] Write failing tests for pure analytics behavior.
- [ ] Implement `volcon/models.py` and `volcon/calculator.py` until tests pass.
- [ ] Write failing provider tests for sample data and Tradier JSON normalization.
- [ ] Implement `volcon/providers.py` until tests pass.
- [ ] Implement `scripts/update_data.py` and generate committed sample output.
- [ ] Build static dashboard files using the generated JSON contract.
- [ ] Add GitHub Pages workflow and repository docs.
- [ ] Run `pytest`, updater, and local static-server smoke checks.
- [ ] Create GitHub repository, push `main`, configure Pages workflow, and report deployment status.

## Self-Review

The plan covers data ingestion, analytics, public output, UI, daily automation, risk messaging, and deployment. It avoids placeholders by naming exact files and expected behavior. It keeps raw provider data out of public Pages output and labels sample fallback clearly.

