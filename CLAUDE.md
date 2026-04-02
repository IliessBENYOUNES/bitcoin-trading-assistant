# 🤖 CLAUDE.md — Règles Agent IA (Bitcoin Trading Assistant)

> Ce fichier est la **source unique de vérité** pour tout agent IA travaillant sur ce projet.
> Il fusionne et remplace le contenu de AGENT.md (conservé pour compatibilité).
> **Version :** v0.9.0 — Dernière mise à jour : 2 avril 2026

---

## 📖 Contexte du projet

**Bitcoin Trading Assistant** (alias **BTC Insight**) est un outil d'aide à la lecture du marché Bitcoin.

| Élément | Valeur |
|---------|--------|
| Backend | FastAPI 0.109 + SQLAlchemy 2.0 + Python 3.12 |
| Frontend | React 18 + TypeScript 5 + Vite 5 + MUI 5 |
| Base de données | PostgreSQL (prod) / SQLite (tests) |
| Tests backend | **253 tests** pytest, tous passing |
| Frontend build | `tsc --noEmit` sans erreur |
| Phase courante | **v0.9 livré** — Étape 1 BTC Insight complète, prochaine étape v1.0 |

**Documents à lire en premier :**
1. Ce fichier (`CLAUDE.md`) — Règles de l'agent
2. `docs/CURRENT_STATE.md` — État technique complet
3. `docs/ROADMAP.md` — Roadmap par phases

---

## 🔒 Règle de sécurité Git obligatoire

> **C'est la règle la plus importante. Elle prime sur tout le reste.**

1. Travaille uniquement par **blocs fonctionnels cohérents**.
2. À la fin de chaque gros bloc terminé et stabilisé :
   - Lance les **tests ciblés pertinents** ;
   - Corrige les **erreurs bloquantes** éventuelles ;
   - Fais un **commit avec un message explicite et structuré** ;
   - **Pousse immédiatement** sur la branche courante.
3. N'enchaîne **jamais** plusieurs blocs majeurs sans commit/push intermédiaire.
4. Si un bloc est **risqué**, fais des sous-checkpoints supplémentaires.
5. Si tu modifies de l'**infra, du tooling, du CI/CD, des seeds, ou des fichiers globaux**, considère cela comme sensible et **isole le bloc**.
6. En cas de doute, privilégie un **commit checkpoint supplémentaire** plutôt qu'un lot trop gros.

---

## Règle n°1 — TOUJOURS mettre à jour les docs avant commit

**Avant chaque commit et push**, l'agent DOIT mettre à jour :

### `docs/CURRENT_STATE.md` (obligatoire) :
- Version courante (si changée)
- Dernier commit (hash + message)
- Date de dernière mise à jour
- Nombre de tests (si ajoutés/supprimés)
- Fonctionnalités livrées (si ajoutées)
- Architecture (si nouveaux fichiers/dossiers)
- "Ce qui n'est PAS encore fait" (si une feature est complétée)
- Problèmes connus (si résolus ou nouveaux)

### `docs/ROADMAP.md` (si une phase change) :
- Marquer la phase livrée avec ✅
- Mettre à jour "PROCHAINE ÉTAPE"
- Mettre à jour la timeline

### `CHANGELOG.md` (si nouvelle version) :
- Ajouter une entrée au format Keep a Changelog
- Sections : Added, Changed, Fixed, Technical

### `docs/requirements_traceability.md` (si nouvelles exigences) :
- Ajouter les nouveaux FR-xxx-yyy avec preuves
- Mettre à jour le compteur de tests

> ⚠️ Un commit sans mise à jour de CURRENT_STATE.md est un commit incomplet.

---

## Règle n°2 — Lancer les tests avant de commit

Avant tout commit :

```bash
# Backend — TOUS les tests doivent passer
cd backend
.\venv\Scripts\activate        # Windows
python -m pytest tests/ -v

# Frontend — Zéro erreur TypeScript
cd frontend
npx tsc --noEmit
```

Vérifier :
- ✅ **253+ tests** backend passent (le nombre ne doit jamais diminuer)
- ✅ Aucun nouveau test en échec
- ✅ `tsc --noEmit` sans erreur
- Si des tests échouent → **corriger avant de commit**

---

## Règle n°3 — Messages de commit conventionnels

Format [Conventional Commits](https://www.conventionalcommits.org/) :

```
<type>(<scope>): <description courte>
```

Types autorisés :
| Type | Usage |
|------|-------|
| `feat` | Nouvelle fonctionnalité |
| `fix` | Correction de bug |
| `docs` | Documentation uniquement |
| `test` | Ajout/modification de tests |
| `refactor` | Refactoring sans changement fonctionnel |
| `chore` | Maintenance (deps, config, cleanup) |
| `style` | Formatage, pas de changement de logique |

Exemples :
```
feat(signals): add signal engine with composite score v0.7
feat(alerts): add alert system with CRUD + check engine v0.8
fix(market): fix get_timeframe_hours function definition lost in merge
docs: update CURRENT_STATE.md for v0.8.0
test(alerts): add 48 tests for alert CRUD, check, and endpoints
```

---

## Règle n°4 — Ne jamais casser l'existant

Avant de modifier du code existant :
1. **Lire** le fichier complet avant d'éditer
2. **Comprendre** le contexte (pourquoi ce code existe)
3. **Vérifier** les imports et dépendances
4. **Tester** après modification

⚠️ **Piège connu :** lors de l'insertion de nouveau code entre deux fonctions, vérifier que la fonction suivante garde bien sa déclaration `def`. Des fusions accidentelles de blocs de code ont déjà causé des bugs (ex: `get_timeframe_hours` perdue dans `get_signals`).

Ne pas :
- ❌ Supprimer du code sans comprendre son rôle
- ❌ Changer des signatures de fonction sans vérifier les appelants
- ❌ Modifier la structure de la DB sans migration
- ❌ Fusionner du code de deux fonctions différentes par mégarde

---

## Règle n°5 — Respecter l'architecture existante

### Backend
```
backend/app/
├── api/routes/     → Endpoints FastAPI (routing + validation uniquement)
│   ├── health.py   → GET /health, /health/db
│   ├── market.py   → GET /market/candles, indicators, signals, gaps, price, info
│   ├── alerts.py   → GET/POST/PUT/DELETE /alerts, POST /alerts/check
│   ├── news.py     → GET /news, GET /news/sentiment
│   └── scheduler.py → GET /scheduler/status, POST trigger
├── services/       → Logique métier (calculs, interprétation, appels externes)
│   ├── coingecko_service.py  → Client HTTP CoinGecko
│   ├── indicator_service.py  → RSI, MACD, SMA, Bollinger
│   ├── signal_service.py     → Interprétation → signaux + score composite
│   ├── alert_service.py      → CRUD alertes + évaluation conditions
│   ├── news_service.py       → Collecte RSS + sentiment + impact
│   └── resample_service.py   → Agrégation OHLCV
├── models/         → Modèles SQLAlchemy (DB) — exposés via __init__.py
│   ├── candle.py   → Table candles (OHLCV + timeframe)
│   └── alert.py    → Table alerts (conditions + status)
├── schemas/        → Schémas Pydantic (validation/sérialisation) — exposés via __init__.py
│   ├── candle.py   → Schémas candle
│   ├── signal.py   → Schémas signal (SignalItem, CompositeScore)
│   ├── alert.py    → Schémas alert (AlertCreate, AlertResponse, AlertCheck)
│   └── news.py     → Schémas news (NewsItem, NewsSentimentSummary, NewsResponse)
├── tasks/          → Jobs planifiés (APScheduler)
└── utils/          → Utilitaires réutilisables (time_buckets, db_upsert)
```

### Frontend
```
frontend/src/
├── pages/          → Pages (1 par route, ex: Dashboard.tsx)
├── components/     → Composants réutilisables (IndicatorPanel, SignalPanel, AlertPanel, NewsPanel, etc.)
├── hooks/          → Custom hooks React (useIndicators, useSignals, useAlerts, useNews, etc.)
├── api/            → Appels API typés (marketApi.ts avec fonctions async)
└── types/          → Types TypeScript partagés (api.ts + index.ts barrel)
```

### Conventions de nommage
| Couche | Convention | Exemple |
|--------|-----------|---------|
| Service Python | `class XxxService` avec `__init__(self, db)` | `AlertService(db).check_alerts()` |
| Schema Python | Classes Pydantic dans `schemas/xxx.py` | `AlertCreate`, `AlertResponse` |
| Endpoint Python | Fonction dans `routes/xxx.py` avec `@router.get` | `def list_alerts(...)` |
| Hook React | `useXxx` retournant `{ data, loading, error, refresh }` | `useAlerts({ timeframe, pollInterval })` |
| Composant React | `XxxPanel` ou `XxxChip` avec props typées | `<AlertPanel ... />` |
| API client | `getXxx(params, options)` dans `marketApi.ts` | `getAlerts()`, `checkAlerts()` |
| Types TS | Interface dans `types/api.ts` | `AlertItem`, `AlertCheckResponse` |

### Pattern d'ajout d'une nouvelle feature (checklist)

Pour ajouter une nouvelle feature full-stack (ex: signaux, alertes...) :

**Backend :**
1. `models/xxx.py` — Modèle SQLAlchemy (si nouvelle table)
2. `models/__init__.py` — Ajouter l'export
3. `schemas/xxx.py` — Schémas Pydantic (request/response)
4. `schemas/__init__.py` — Ajouter les exports
5. `services/xxx_service.py` — Logique métier
6. `api/routes/xxx.py` — Endpoints FastAPI
7. `api/routes/__init__.py` — Ajouter le router
8. `main.py` — Inclure le router
9. `tests/test_xxx.py` — Tests unitaires + intégration + endpoint

**Frontend :**
10. `types/api.ts` — Types TypeScript
11. `api/marketApi.ts` — Fonctions API
12. `hooks/useXxx.ts` — Hook React
13. `components/XxxPanel.tsx` — Composant UI
14. `pages/Dashboard.tsx` — Intégration dans le layout

**Docs :**
15. `docs/CURRENT_STATE.md` — Mettre à jour
16. `CHANGELOG.md` — Nouvelle entrée
17. `docs/ROADMAP.md` — Marquer comme livré
18. `docs/requirements_traceability.md` — Nouvelles exigences

---

## Règle n°6 — Documenter les décisions

Si un choix technique non trivial est fait, ajouter un commentaire **pourquoi** :

```python
# On utilise upsert au lieu de insert pour garantir l'idempotence
# du resample : relancer le job ne crée pas de doublons
```

---

## Règle n°7 — Pas de secrets dans le code

- ❌ Jamais de clés API, mots de passe ou tokens dans le code
- ✅ Utiliser les variables d'environnement via `.env` et `config.py`
- Le fichier `.env` est dans le `.gitignore`

Variables d'environnement utilisées :
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///./test.db` | URL de la base de données |
| `DEBUG` | `true` | Active les docs API + CORS permissif |
| `SCHEDULER_ENABLED` | `true` | Active/désactive le scheduler |
| `SCHEDULER_INTERVAL_4H` | `240` | Intervalle job 4h (minutes) |
| `SCHEDULER_INTERVAL_30M` | `30` | Intervalle job 30m (minutes) |
| `VITE_API_BASE_URL` | `http://localhost:8000` | URL backend pour le frontend |

---

## Règle n°8 — Consulter la roadmap avant d'implémenter

Avant d'ajouter une feature :
1. Lire `docs/ROADMAP.md` pour la phase courante
2. Lire `docs/ROADMAP_INFINI.md` pour la vision long terme
3. S'assurer que la feature s'inscrit dans la bonne phase

**Phase actuelle : v0.9 livré — Prochaine étape v1.0 Moteur de Décision**

Ne pas implémenter une feature d'une phase future si la phase courante n'est pas terminée.

---

## Règle n°9 — Garder les dépendances à jour

Si une nouvelle dépendance Python est utilisée :
```bash
pip install <package>
pip freeze | grep <package> >> requirements.txt  # Avec version pinned
```

Si une nouvelle dépendance npm est utilisée :
```bash
npm install <package>  # Automatiquement ajouté à package.json
```

---

## Règle n°10 — Préférer la simplicité

- Un code simple et lisible > un code clever et compact
- Pas d'abstraction prématurée
- Pas de design pattern si un `if` suffit
- Le code le plus facile à maintenir est celui qu'on n'écrit pas

---

## Règle n°11 — Tester les endpoints après ajout

Après avoir ajouté un endpoint, **toujours vérifier** qu'il est accessible :

```bash
# Lister toutes les routes enregistrées
python -c "from app.main import app; [print(r.path, r.methods) for r in app.routes if hasattr(r, 'path')]"
```

⚠️ Si le serveur tourne avec `--reload`, un changement de fichier **peut ne pas être rechargé** si le module a une erreur de syntaxe silencieuse. En cas de doute, **redémarrer le serveur**.

---

## Règle n°12 — Conventions de tests

### Structure des fichiers de test
```python
import pytest
from app.services.xxx_service import XxxService

class TestInterpreterXxx:
    """Tests pour interpret_xxx."""
    def test_xxx_none_returns_none(self): ...

class TestXxxServiceIntegration:
    """Tests d'intégration avec vraie DB."""
    def test_with_real_db(self, db_session): ...

class TestXxxEndpoint:
    """Tests endpoint API."""
    def test_endpoint_returns_200(self, client): ...
```

### Fixtures disponibles (dans `conftest.py`)
| Fixture | Description |
|---------|-------------|
| `db_session` | Session SQLite en mémoire, reset par test |
| `client` | TestClient FastAPI avec override DB |

### Conventions
- Tester les cas limites : `None`, vide, boundary values
- Tester l'intégration avec vraie DB (pas que des mocks)
- Tester l'endpoint HTTP (status code + structure réponse)
- Nommer les tests en français dans les docstrings

---

## Problèmes connus à ne PAS réintroduire

| # | Problème | Comment l'éviter |
|---|----------|------------------|
| 1 | Fonction `get_timeframe_hours` perdue lors d'un insert de code | Toujours vérifier que les fonctions adjacentes gardent leur `def` |
| 2 | Serveur `--reload` qui ne prend pas les changements | Redémarrer uvicorn en cas de 404 inattendu |
| 3 | CHANGELOG.md avec des commandes shell en tête | Ne jamais écrire de commandes avant le `# Changelog` |
| 4 | Warnings pytest `_fetch_and_store` non awaited | Cosmétique, ne pas corriger sans comprendre le scheduler async |

---

## Checklist pré-commit

```
[ ] Tests backend passent (253+ tests, python -m pytest tests/ -v)
[ ] Frontend compile (npx tsc --noEmit, zéro erreur)
[ ] docs/CURRENT_STATE.md mis à jour
[ ] CHANGELOG.md mis à jour (si nouvelle version)
[ ] docs/ROADMAP.md mis à jour (si phase change)
[ ] docs/requirements_traceability.md mis à jour (si nouvelles exigences)
[ ] Message de commit conventionnel
[ ] Pas de secrets dans le code
[ ] Pas de fichiers temporaires (.pyc, node_modules, .idea, test.db)
[ ] Endpoints testés et accessibles (pas de 404 surprise)
[ ] Commit poussé immédiatement sur la branche courante
```

---

## Commandes utiles

```bash
# Backend — Démarrer
cd backend && .\venv\Scripts\activate && uvicorn app.main:app --reload --port 8000

# Frontend — Démarrer
cd frontend && npm run dev

# Tests backend
cd backend && python -m pytest tests/ -v

# TypeScript check
cd frontend && npx tsc --noEmit

# Lister les routes FastAPI
cd backend && python -c "from app.main import app; [print(r.path, r.methods) for r in app.routes if hasattr(r, 'path')]"

# Compter les tests
cd backend && python -m pytest tests/ --co -q | tail -1

# Git — Commit bloc fonctionnel
git add -A && git commit -m "feat(scope): description" && git push
```

