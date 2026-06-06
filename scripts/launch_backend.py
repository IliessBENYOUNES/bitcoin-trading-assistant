#!/usr/bin/env python
"""
Lanceur de backend robuste pour les 2 moteurs BTC.

Pourquoi : les `backend/.env` des deux repos pointent (par erreur) vers la base
`societe_saas` d'un autre projet, avec un suffixe Prisma `?schema=public` que
psycopg2 refuse. Ce lanceur lit `DATABASE_URL` du `.env` AU RUNTIME, force le
bon nom de base et retire la query string — SANS modifier le `.env` et sans
jamais exposer le mot de passe. Idempotent : si le `.env` est déjà correct,
le résultat est identique (no-op).

Usage :
    python scripts/launch_backend.py --engine exp     # -> bitcoin_experiment, port 8001
    python scripts/launch_backend.py --engine main    # -> bitcoin_assistant,  port 8000
À lancer avec le venv DU repo correspondant (uvicorn + deps).
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlsplit, urlunsplit

ENGINES = {
    "main": (r"C:\Users\ilies\git\bitcoin-trading-assistant\backend", "bitcoin_assistant", 8000),
    "exp": (r"C:\Users\ilies\git\bitcoin-trading-v2-experiment\backend", "bitcoin_experiment", 8001),
}


def read_database_url(backend: str) -> str | None:
    envp = os.path.join(backend, ".env")
    if not os.path.exists(envp):
        return None
    try:
        from dotenv import dotenv_values
        v = dotenv_values(envp).get("DATABASE_URL")
        if v:
            return v
    except Exception:
        pass
    with open(envp, encoding="utf-8") as f:
        for line in f:
            s = line.lstrip()
            if s.startswith("DATABASE_URL") and "=" in s and not s.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=list(ENGINES))
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--no-scheduler", action="store_true")
    args = ap.parse_args()

    backend, dbname, default_port = ENGINES[args.engine]
    port = args.port or default_port
    os.chdir(backend)
    sys.path.insert(0, backend)

    raw = read_database_url(backend)
    if raw:
        u = urlsplit(raw.split("?", 1)[0])
        os.environ["DATABASE_URL"] = urlunsplit((u.scheme, u.netloc, "/" + dbname, "", ""))
        print(f"[launch] engine={args.engine} -> db={dbname} (host={u.hostname}:{u.port}) port={port}", flush=True)
    else:
        print(f"[launch] ⚠ pas de DATABASE_URL dans .env — utilise la config par defaut", flush=True)

    if not args.no_scheduler:
        os.environ.setdefault("SCHEDULER_ENABLED", "true")

    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=False, log_level="info")


if __name__ == "__main__":
    main()
