# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-24

### Added
- Modular FastAPI architecture (split from single `app.py` into 15+ modules)
- SQLite database with migration system (10 tables, versioned migrations)
- Canonical Model normalization with alias support
- Static model capability scoring (YAML-configurable, 10 capability dimensions)
- Rule-based request classifier (task type + difficulty + capability extraction)
- Dynamic health monitoring (Beta/Wilson reliability, multi-window aggregation)
- Circuit breaker state machine (closed → open → half-open → closed)
- Smart routing engine (filter → model select → provider select)
- Logical models: auto, auto-fast, auto-best, auto-coding, auto-reasoning, auto-writing, auto-translation, auto-vision, auto-tools
- Provider key encryption (Fernet) with master key
- Client API keys (hash storage, RPM limiting, model permissions)
- Admin/Client authentication separation
- Streaming safety (first-token failover, post-token safe termination)
- Web dashboard (Overview, Providers, Models, Health, Routing, Client Keys)
- Docker deployment (Dockerfile, compose.yaml, health checks)
- Versioned deploy/rollback scripts with database backup
- GitHub Actions CI (ruff, mypy, pytest, docker build)
- GitHub Actions Security (gitleaks, dependency scan, image scan)
- GitHub Actions Release (versioned images, GitHub Release)
- Fake upstream test providers (fast, slow, flaky)
- Comprehensive test suite (unit, integration, streaming)
- LEGAL_NOTES.md (CC BY-NC 4.0 compliance)

### Changed
- Forked from `zk-2025/model-gateway` v1.6.0 (commit 021b259)
- Renamed `quality_score` to `route_reliability` / `availability_score`
- New routes use Beta prior (cold-start) instead of optimistic 100%

### Removed
- Forced Chinese language injection (`ensure_lang_reply`)
- Desktop app mode (pywebview, pystray, Pillow)
- Cross-model streaming continuation (replaced with safe termination)
- Remote preset/announcement fetch from Gitee
- Online exe update mechanism

[Unreleased]: https://github.com/AnnaTianPM/model-gateway/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/AnnaTianPM/model-gateway/releases/tag/v0.1.0
