#!/usr/bin/env python
"""
Continuous journal exporter for BTC Insight / INFINI paper-trading runs.

This utility polls one or several running backends and stores immutable
journal snapshots under docs/journaux.

It deliberately uses only the Python standard library so it can run from the
existing project environment without installing extra dependencies.

Default engines:
- MAIN          -> http://127.0.0.1:8000, frontend PORT5173
- EXPERIMENTAL  -> http://127.0.0.1:8001, frontend PORT5174

Typical usage:
    python scripts/continuous_journal_exporter.py --once
    python scripts/continuous_journal_exporter.py --interval-seconds 3600
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EngineConfig:
    """Runtime identity of one paper-trading engine."""

    name: str
    backend_url: str
    frontend_port: int
    repo_path: Path | None = None


@dataclass(frozen=True)
class GitInfo:
    """Minimal git signature used to identify which code produced a run."""

    branch: str
    sha: str
    dirty: bool
    repo_path: str | None

    @property
    def signature(self) -> str:
        return f"{self.branch}-{self.sha}"


def utc_now() -> datetime:
    """Return a timezone-aware UTC datetime."""

    return datetime.now(timezone.utc)


def iso_for_filename(dt: datetime) -> str:
    """Return an ISO-ish timestamp that is safe on Windows filenames."""

    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def sanitize_slug(value: str | None, fallback: str = "unknown") -> str:
    """Normalize arbitrary text so it is safe in filenames."""

    text = (value or fallback).strip()
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or fallback


def project_root_from_script() -> Path:
    """Return the repository root based on this script location."""

    return Path(__file__).resolve().parents[1]


def run_git(repo_path: Path, args: list[str]) -> str | None:
    """Run a git command and return stdout, or None when unavailable."""

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return result.stdout.strip()
    except Exception:
        return None


def get_git_info(repo_path: Path | None) -> GitInfo:
    """Read branch, short SHA and dirty flag for a repo/worktree."""

    if repo_path is None or not repo_path.exists():
        return GitInfo(branch="unknown", sha="unknown", dirty=False, repo_path=str(repo_path) if repo_path else None)

    branch = run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    sha = run_git(repo_path, ["rev-parse", "--short", "HEAD"]) or "unknown"
    status = run_git(repo_path, ["status", "--porcelain"]) or ""

    return GitInfo(
        branch=sanitize_slug(branch),
        sha=sanitize_slug(sha),
        dirty=bool(status.strip()),
        repo_path=str(repo_path),
    )


def fetch_json(url: str, timeout_seconds: int) -> Any:
    """Fetch a JSON endpoint with a strict timeout."""

    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


def safe_relative(path: Path, root: Path) -> str:
    """Return path relative to root when possible, otherwise absolute string."""

    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def atomic_write_json(path: Path, payload: Any) -> None:
    """Write JSON atomically to avoid half-written snapshots."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp_path.replace(path)


def append_jsonl(path: Path, payload: Any) -> None:
    """Append one JSON object per line to a stream file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")


def summarize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a compact summary for manifests and terminal output."""

    account = payload.get("account") or {}
    metrics = payload.get("metrics") or {}
    closed_trades = payload.get("closed_trades") or []
    open_trades = payload.get("open_trades") or []

    fee_sum = 0.0
    gross_sum = 0.0
    net_sum = 0.0
    closed_count = 0
    gross_positive_net_negative = 0

    for trade in closed_trades:
        if not isinstance(trade, dict):
            continue
        closed_count += 1
        fees = float(trade.get("trading_fees") or 0.0)
        gross = float(trade.get("gross_pnl") or 0.0)
        net = float(trade.get("pnl") or 0.0)
        fee_sum += fees
        gross_sum += gross
        net_sum += net
        if gross > 0 and net < 0:
            gross_positive_net_negative += 1

    account_total_fees = float(account.get("total_fees") or 0.0)
    fee_gap = account_total_fees - fee_sum

    return {
        "total_trades": payload.get("total_trades", metrics.get("total_trades")),
        "closed_trades": closed_count,
        "open_trades": len(open_trades) if isinstance(open_trades, list) else None,
        "account_total_pnl": account.get("total_pnl"),
        "metrics_net_pnl": metrics.get("net_pnl"),
        "closed_net_pnl_sum": round(net_sum, 6),
        "closed_gross_pnl_sum": round(gross_sum, 6),
        "account_total_fees": round(account_total_fees, 6),
        "closed_trading_fees_sum": round(fee_sum, 6),
        "fees_gap_account_minus_trades": round(fee_gap, 6),
        "win_rate": metrics.get("win_rate"),
        "profit_factor": metrics.get("profit_factor"),
        "buy_hold_pnl_pct": metrics.get("buy_hold_pnl_pct"),
        "gross_positive_net_negative_trades": gross_positive_net_negative,
    }


def build_snapshot_filename(captured_at: datetime, engine: EngineConfig, git_info: GitInfo) -> str:
    """Build the immutable snapshot filename."""

    timestamp = iso_for_filename(captured_at)
    engine_name = sanitize_slug(engine.name.upper())
    signature = sanitize_slug(git_info.signature)
    return f"btc-trading-journal-{timestamp}-{engine_name}-PORT{engine.frontend_port}-{signature}.json"


def build_stream_filename(engine: EngineConfig, git_info: GitInfo) -> str:
    """Build the append-only stream filename for one engine/code signature."""

    engine_name = sanitize_slug(engine.name.upper())
    signature = sanitize_slug(git_info.signature)
    return f"btc-trading-journal-stream-{engine_name}-PORT{engine.frontend_port}-{signature}.jsonl"


def export_engine(
    engine: EngineConfig,
    output_dir: Path,
    timeout_seconds: int,
    main_repo_root: Path,
) -> dict[str, Any]:
    """Export one engine snapshot and return manifest entry."""

    captured_at = utc_now()
    git_info = get_git_info(engine.repo_path or main_repo_root)
    endpoint = engine.backend_url.rstrip("/") + "/paper/trades/export"

    meta = {
        "snapshot_id": f"{sanitize_slug(engine.name.upper())}-{iso_for_filename(captured_at)}",
        "captured_at": captured_at.isoformat(),
        "engine": engine.name.upper(),
        "backend_url": engine.backend_url.rstrip("/"),
        "frontend_port": engine.frontend_port,
        "export_endpoint": endpoint,
        "git": {
            "branch": git_info.branch,
            "sha": git_info.sha,
            "dirty": git_info.dirty,
            "repo_path": git_info.repo_path,
        },
    }

    try:
        payload = fetch_json(endpoint, timeout_seconds)
        if not isinstance(payload, dict):
            raise ValueError(f"Unexpected JSON root type: {type(payload).__name__}")

        payload = dict(payload)
        payload["_snapshot_meta"] = {**meta, "status": "ok"}
        summary = summarize_payload(payload)

        snapshots_dir = output_dir / "live-snapshots"
        stream_dir = output_dir / "live-streams"
        snapshot_path = snapshots_dir / build_snapshot_filename(captured_at, engine, git_info)
        stream_path = stream_dir / build_stream_filename(engine, git_info)

        atomic_write_json(snapshot_path, payload)
        append_jsonl(stream_path, {"_snapshot_meta": payload["_snapshot_meta"], "summary": summary, "payload": payload})

        return {
            "engine": engine.name.upper(),
            "status": "ok",
            "captured_at": captured_at.isoformat(),
            "snapshot_file": safe_relative(snapshot_path, main_repo_root),
            "stream_file": safe_relative(stream_path, main_repo_root),
            "summary": summary,
            "git": payload["_snapshot_meta"]["git"],
        }

    except Exception as exc:
        error_payload = {
            "_snapshot_meta": {**meta, "status": "error"},
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }
        errors_dir = output_dir / "live-errors"
        error_path = errors_dir / build_snapshot_filename(captured_at, engine, git_info)
        atomic_write_json(error_path, error_payload)

        return {
            "engine": engine.name.upper(),
            "status": "error",
            "captured_at": captured_at.isoformat(),
            "error_file": safe_relative(error_path, main_repo_root),
            "error": error_payload["error"],
            "git": error_payload["_snapshot_meta"]["git"],
        }


def write_manifest(output_dir: Path, main_repo_root: Path, entries: list[dict[str, Any]]) -> None:
    """Write/overwrite the latest manifest for quick discovery."""

    manifest_path = output_dir / "live-export-manifest.json"
    manifest = {
        "manifest_version": "1.0",
        "updated_at": utc_now().isoformat(),
        "description": "Latest hourly paper-trading journal exports by engine.",
        "engines": {entry["engine"]: entry for entry in entries},
    }
    atomic_write_json(manifest_path, manifest)
    print(f"[journal-exporter] manifest -> {safe_relative(manifest_path, main_repo_root)}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""

    root = project_root_from_script()
    default_exp_repo = Path(os.environ.get("BTC_EXPERIMENT_REPO", r"C:\Users\ilies\git\bitcoin-trading-v2-experiment"))

    parser = argparse.ArgumentParser(description="Export MAIN and EXPERIMENTAL paper-trading journals periodically.")
    parser.add_argument("--interval-seconds", type=int, default=3600, help="Delay between export cycles. Default: 3600.")
    parser.add_argument("--once", action="store_true", help="Export once immediately, then exit.")
    parser.add_argument("--output-dir", type=Path, default=root / "docs" / "journaux", help="Output directory.")
    parser.add_argument("--timeout-seconds", type=int, default=20, help="HTTP timeout per endpoint.")
    parser.add_argument("--main-url", default=os.environ.get("BTC_MAIN_BACKEND_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--experimental-url", default=os.environ.get("BTC_EXPERIMENT_BACKEND_URL", "http://127.0.0.1:8001"))
    parser.add_argument("--main-repo", type=Path, default=root)
    parser.add_argument("--experimental-repo", type=Path, default=default_exp_repo)
    parser.add_argument("--skip-main", action="store_true", help="Do not export MAIN.")
    parser.add_argument("--skip-experimental", action="store_true", help="Do not export EXPERIMENTAL.")
    return parser.parse_args(argv)


def build_engines(args: argparse.Namespace) -> list[EngineConfig]:
    """Build engine list from CLI flags."""

    engines: list[EngineConfig] = []
    if not args.skip_main:
        engines.append(EngineConfig("MAIN", args.main_url, 5173, args.main_repo))
    if not args.skip_experimental:
        engines.append(EngineConfig("EXPERIMENTAL", args.experimental_url, 5174, args.experimental_repo))
    return engines


def export_cycle(args: argparse.Namespace, engines: list[EngineConfig], root: Path) -> list[dict[str, Any]]:
    """Run one export cycle for all configured engines."""

    print(f"[journal-exporter] export cycle started at {utc_now().isoformat()}")
    entries = [
        export_engine(
            engine=engine,
            output_dir=args.output_dir,
            timeout_seconds=args.timeout_seconds,
            main_repo_root=root,
        )
        for engine in engines
    ]
    write_manifest(args.output_dir, root, entries)

    for entry in entries:
        engine = entry["engine"]
        if entry["status"] == "ok":
            summary = entry.get("summary") or {}
            print(
                "[journal-exporter] "
                f"{engine}: OK trades={summary.get('total_trades')} "
                f"net={summary.get('metrics_net_pnl')} "
                f"fees_sum={summary.get('closed_trading_fees_sum')} "
                f"file={entry.get('snapshot_file')}"
            )
        else:
            print(f"[journal-exporter] {engine}: ERROR {entry.get('error')}", file=sys.stderr)

    return entries


def main(argv: list[str] | None = None) -> int:
    """Program entrypoint."""

    args = parse_args(argv or sys.argv[1:])
    root = project_root_from_script()
    args.output_dir = args.output_dir.resolve()

    engines = build_engines(args)
    if not engines:
        print("[journal-exporter] No engine configured. Nothing to do.", file=sys.stderr)
        return 2

    if args.interval_seconds <= 0:
        print("[journal-exporter] --interval-seconds must be > 0", file=sys.stderr)
        return 2

    print("[journal-exporter] repository root:", root)
    print("[journal-exporter] output dir:", args.output_dir)
    print("[journal-exporter] engines:", ", ".join(f"{e.name}={e.backend_url}" for e in engines))

    while True:
        export_cycle(args, engines, root)

        if args.once:
            return 0

        print(f"[journal-exporter] sleeping {args.interval_seconds}s")
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
