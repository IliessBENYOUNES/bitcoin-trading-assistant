# 🚦 AGENT_RUNBOOK — Reprise immédiate de session

> **À LIRE EN PREMIER** à chaque nouvelle session, et systématiquement quand l'utilisateur dit
> « analyse le projet », « reprends », « où on en est ». Ce fichier permet de reprendre le travail
> instantanément après un reboot ou la fermeture du terminal PowerShell.
>
> **Dernière mise à jour :** 6 juin 2026 — fin de session moteur **v2.1.0** (gate économique).
> **Règle :** mettre ce fichier à jour à la FIN de chaque session (section §1 + §9).

---

## 0. TL;DR — les commandes de reprise (à lancer en premier)

```bash
# 1) État git (les 2 worktrees)
git -C /c/Users/ilies/git/bitcoin-trading-assistant      log --oneline -3   # MAIN (master)
git -C /c/Users/ilies/git/bitcoin-trading-v2-experiment  log --oneline -3   # EXP  (experiment/v2-fees-and-1m)
git -C /c/Users/ilies/git/bitcoin-trading-v2-experiment  status --short

# 2) Les 4 serveurs tournent-ils ?
netstat -ano | grep LISTENING | grep -E ":8000|:8001|:5173|:5174"

# 3) État des moteurs
curl -s http://127.0.0.1:8001/paper/engine-mode             # EXP -> doit être "experimental"
curl -s http://127.0.0.1:8001/paper/autonomous/status       # EXP -> running, tick_count
curl -s http://127.0.0.1:8000/paper/autonomous/status       # MAIN -> running
curl -s http://127.0.0.1:8001/paper/metrics                 # perf EXP
```

Si rien n'écoute → voir **§4 (Relancer tout)**.

---

## 1. Où on en est (état courant)

- **Moteur v2.1.0** mergé & poussé : commit **`716ee44`** sur `experiment/v2-fees-and-1m`.
  Le moteur multi-stratégie est désormais **fee-positive par construction** (gate économique pré-trade :
  aucun trade ne s'ouvre si TP < 2× frais round-trip = 0.62 %). Détails : `CHANGELOG.md [2.1.0]` + `docs/HANDOFF_GPT.md`.
- **2 moteurs lancés en parallèle** (paper trading, headless, ticks 60 s) :
  - **MAIN** (port 8000) = moteur **standard**, profil **scalping** (1 stratégie). DB `bitcoin_assistant`.
  - **EXP** (port 8001) = moteur **multi-stratégie** (5 stratégies orchestrées). DB `bitcoin_experiment`.
- **WIP v2.0.32 non-commitée** dans EXP (`trading_profile_service.py` + `paper_trading_service.py`,
  profils standard balanced/aggressive). **NE PAS la committer** avec le moteur ; orthogonale au multi-stratégie.

---

## 2. Architecture & emplacements

| | MAIN | EXP (travail courant) |
|---|---|---|
| Dossier | `C:\Users\ilies\git\bitcoin-trading-assistant` | `C:\Users\ilies\git\bitcoin-trading-v2-experiment` |
| Branche | `master` | `experiment/v2-fees-and-1m` |
| Backend | port **8000** | port **8001** |
| Frontend | port **5173** → http://localhost:5173 | port **5174** → http://localhost:5174 |
| Base PostgreSQL | `bitcoin_assistant` (34k bougies) | `bitcoin_experiment` (1.7k bougies) |
| Moteur | standard (profils + slots) | **multi-stratégie** (`engine-mode=experimental`) |
| venv | `backend/venv/Scripts/python.exe` | `backend/venv/Scripts/python.exe` |

Le **multi-stratégie n'existe QUE sur EXP** (sur `master`, `GET /paper/engine-mode` renvoie 404).
Préfixe API = **`/paper`** (pas `/paper-trading`). PostgreSQL tourne en service local (port 5432).

---

## 3. ⚠️ Pièges environnementaux (CRITIQUE — lire avant d'agir)

1. **`backend/.env` mal configuré (LES DEUX repos).** `DATABASE_URL` pointe par erreur vers
   `postgresql://...@localhost:5432/societe_saas?schema=public` — base d'un **autre projet** (128 tables).
   - **NE JAMAIS** lancer le backend bitcoin tel quel (il polluerait `societe_saas`), **NE JAMAIS** toucher `societe_saas`.
   - Les bonnes bases existent déjà (mêmes identifiants) : `bitcoin_assistant` (MAIN), `bitcoin_experiment` (EXP).
   - Contournement **sans éditer `.env`** : les lanceurs (§4 + Annexe) surchargent `DATABASE_URL` au runtime
     (remplacent le nom de base + retirent le suffixe Prisma `?schema=...` que psycopg2 refuse ; `database.py` = `create_engine` synchrone).
   - **À corriger proprement** quand possible : dans chaque `backend/.env`, mettre la bonne base et retirer `?schema=public`.
2. **Feed de données externe HS.** Le fetch de bougies échoue (`CoinGecko: aucune donnée OHLC reçue`
   et `Binance klines: aucune donnée`). Conséquence : bougies figées au **2026-05-01**, prix « live » statique
   ($77 961 = dernière bougie). Le moteur tourne et **gate** correctement, mais **ne produit pas de trades live
   exploitables** tant que le feed n'est pas rétabli. Vérifier : `curl -s -X POST http://127.0.0.1:8001/scheduler/trigger/4h` puis `GET /scheduler/status` (champ `last_result`).
3. **Gate horaire** : le moteur bloque toute entrée entre **13h et 16h UTC** (`BLOCKED_HOURS_UTC`, audit 17/04).
   En journée UTC 13-16h, `action=hold` avec raison « Blocked hour » est **normal**.
4. **Tests** : lancer pytest avec `DATABASE_URL="sqlite:///./_tmp.db"` sinon erreur DSN Postgres (voir §6).

---

## 4. Relancer TOUT (après reboot / fermeture du terminal)

> Les lanceurs Python (`C:\Users\ilies\AppData\Local\Temp\btc_launch_{exp,main}.py`) gèrent le routage DB.
> **Si `%TEMP%` a été nettoyé au reboot, recréer ces fichiers depuis l'Annexe ci-dessous.**

### 4a. Backends (PowerShell — fenêtres séparées, logs persistants)
```powershell
# EXP backend (8001) -> bitcoin_experiment
Start-Process powershell -ArgumentList '-NoExit','-Command', `
  'C:\Users\ilies\git\bitcoin-trading-v2-experiment\backend\venv\Scripts\python.exe C:\Users\ilies\AppData\Local\Temp\btc_launch_exp.py *>&1 | Tee-Object C:\Users\ilies\btc_exp_backend.log'
# MAIN backend (8000) -> bitcoin_assistant
Start-Process powershell -ArgumentList '-NoExit','-Command', `
  'C:\Users\ilies\git\bitcoin-trading-assistant\backend\venv\Scripts\python.exe C:\Users\ilies\AppData\Local\Temp\btc_launch_main.py *>&1 | Tee-Object C:\Users\ilies\btc_main_backend.log'
```

### 4b. Frontends
```powershell
Start-Process powershell -ArgumentList '-NoExit','-Command', `
  'cd C:\Users\ilies\git\bitcoin-trading-v2-experiment\frontend; $env:VITE_API_BASE_URL="http://localhost:8001"; npx vite --port 5174 --strictPort'
Start-Process powershell -ArgumentList '-NoExit','-Command', `
  'cd C:\Users\ilies\git\bitcoin-trading-assistant\frontend; $env:VITE_API_BASE_URL="http://localhost:8000"; npx vite --port 5173 --strictPort'
```

### 4c. Activer les moteurs (après que /health réponde sur 8000 et 8001)
```bash
# EXP = multi-stratégie
curl -s -X POST "http://127.0.0.1:8001/paper/engine-mode?mode=experimental"
curl -s -X POST "http://127.0.0.1:8001/paper/autonomous/start" -H "Content-Type: application/json" -d '{"interval_seconds":60,"profile":"scalping"}'
# MAIN = scalping (moteur standard)
curl -s -X POST "http://127.0.0.1:8000/paper/autonomous/start" -H "Content-Type: application/json" -d '{"interval_seconds":60,"profile":"scalping"}'
```
Arrêter un moteur : `POST /paper/autonomous/stop`. Tick manuel immédiat : `POST /paper/tick`.

---

## 5. Analyser les journaux & les trades

**Source durable = la base PostgreSQL** (le stdout des serveurs est transitoire). Endpoints clés (sur 8001 pour EXP) :

```bash
curl -s "http://127.0.0.1:8001/paper/journal"               # journal lisible (entrées/sorties + raisons)
curl -s "http://127.0.0.1:8001/paper/trades"                # liste des trades
curl -s "http://127.0.0.1:8001/paper/metrics"               # PnL net, WR, frais, drawdown
curl -s "http://127.0.0.1:8001/paper/diagnostic"            # diagnostic moteur
curl -s "http://127.0.0.1:8001/paper/missed-opportunities"  # entrées ratées
curl -s "http://127.0.0.1:8001/paper/market-context?timeframe=5m"  # ce que le moteur voit
```

Requêtes SQL directes (lecture seule) sur `bitcoin_experiment` (voir Annexe pour le helper de connexion) —
tables utiles : `paper_trade`, `paper_account`, `tick_activity_log`, `learning_signal`, `strategy_feedback`.
Pour comprendre POURQUOI un tick n'a pas tradé : lire le champ `detail`/`rejected_reasons` de `POST /paper/tick`
(ex. « Gate éco scalping … », « Blocked hour », « Range compressé »).

---

## 6. Valider / tester (avant tout commit)

```bash
cd /c/Users/ilies/git/bitcoin-trading-v2-experiment/backend
# Le moteur multi-stratégie (= la cible des changements v2.1.0) :
./venv/Scripts/python.exe -m pytest tests/test_multi_strategy.py -q          # -> 56 passed
# Tests liés au coût / stratégies (SQLite obligatoire sinon erreur DSN) :
DATABASE_URL="sqlite:///./_t.db" ./venv/Scripts/python.exe -m pytest tests/test_economic_value.py -q ; rm -f _t.db
```
**Important** : si le run complet montre ~72 échecs (test_stability / test_scalping_audit / test_micro_stop_loss),
ce sont les tests des **profils standard** cassés par la **WIP v2.0.32 non-commitée** — PAS le moteur.
Preuve : `git stash push -- app/services/trading_profile_service.py app/services/paper_trading_service.py`
puis relancer → **228 passed** ; puis `git stash pop`.

---

## 7. Optimiser le moteur (boucle d'itération)

Leviers (tous dans `backend/app/services/`) :
- **`multi_strategy_engine.py`** — orchestrateur : gate économique (`MIN_EV_MULTIPLE`), cap (`MAX_ELIGIBLE_STRATEGIES`),
  gates globaux (`BLOCKED_HOURS_UTC`, `MIN_ATR_RATIO`, `MAX_ABS_COMBINED_SCORE`), routing `CONTEXT_STRATEGY_MAP`.
- **`strategies/{scalping,micro_scalping,mean_reversion,breakout,aggressive}.py`** — seuils d'entrée + `get_params` (TP/SL/taille/levier/trailing) par stratégie.
- **`experimental_engine.py`** `_manage_open_position` — gestion des positions ouvertes (trailing fee-aware, stale, breakeven).
- **`trading_cost_service.py`** — modèle de coûts (`estimate_economic_viability`, presets de frais).

Process : modifier → `pytest tests/test_multi_strategy.py -q` → observer via `/paper/market-context` + `POST /paper/tick`
→ mesurer via `/paper/metrics` → mettre à jour les 5 docs (cf. CLAUDE.md règles d'or) → commit/push.
Pour une preuve de rentabilité chiffrée : backtest comparatif (`tests/test_backtest.py` + service de backtest) — **nécessite des bougies fraîches** (cf. §3.2).

---

## 8. Checklist « analyse le projet »

1. Lire **ce runbook**, puis `CHANGELOG.md` (dernière version) et `docs/HANDOFF_GPT.md`.
2. `git status` + `git log --oneline -5` sur EXP (vérifier la WIP non-commitée attendue).
3. Vérifier les 4 serveurs (§0.2) + `/health` ; relancer si besoin (§4).
4. Lire perf + trades récents (§5) ; identifier les fuites (frais, stale, sorties prématurées).
5. Choisir le prochain objectif via `docs/ROADMAP.md` ; itérer (§7).

---

## 9. Journal de session (le plus récent en haut)

- **2026-06-06 — v2.1.0** : gate économique pré-trade + trailing fee-aware + cap 2 stratégies + recalibration des 4 stratégies.
  Commit `716ee44` poussé. 4 serveurs lancés, MAIN=scalping / EXP=multi-stratégie. Découvert : `.env` → societe_saas
  (contourné), feed de données externe HS (bougies au 01/05). **Prochaine action** : rétablir le feed de données
  (ou backtester sur les bougies de mai) pour prouver la rentabilité chiffrée de v2.1.0 ; corriger les `.env`.

---

## Annexe — Code des lanceurs (recréer si `%TEMP%` vidé)

**`C:\Users\ilies\AppData\Local\Temp\btc_launch_exp.py`** (pour MAIN : remplacer `BACKEND`, `DBNAME="bitcoin_assistant"`, `PORT=8000`) :
```python
import os, sys
from urllib.parse import urlsplit, urlunsplit
BACKEND = r"C:\Users\ilies\git\bitcoin-trading-v2-experiment\backend"
DBNAME = "bitcoin_experiment"
PORT = 8001
os.chdir(BACKEND); sys.path.insert(0, BACKEND)
raw = None
try:
    from dotenv import dotenv_values
    raw = dotenv_values(os.path.join(BACKEND, ".env")).get("DATABASE_URL")
except Exception:
    pass
if not raw:
    with open(os.path.join(BACKEND, ".env"), encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("DATABASE_URL"):
                raw = line.split("=", 1)[1].strip().strip('"').strip("'"); break
u = urlsplit(raw.split("?", 1)[0])
os.environ["DATABASE_URL"] = urlunsplit((u.scheme, u.netloc, "/" + DBNAME, "", ""))
os.environ["SCHEDULER_ENABLED"] = "true"
import uvicorn
uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, reload=False, log_level="info")
```

**Helper SQL lecture seule** (depuis `backend/`, route vers la bonne base sans exposer le mot de passe) :
```python
from app.config import get_settings
from urllib.parse import urlsplit, urlunsplit
import sqlalchemy as sa
u = urlsplit(get_settings().database_url.split("?", 1)[0])
eng = sa.create_engine(urlunsplit((u.scheme, u.netloc, "/bitcoin_experiment", "", "")))
with eng.connect() as c:
    print(c.execute(sa.text("SELECT count(*) FROM paper_trade")).scalar())
```
