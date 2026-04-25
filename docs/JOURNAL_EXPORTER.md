# Journal Exporter — Exports automatiques des runs paper trading

> Objectif : capturer automatiquement les journaux des deux moteurs pendant qu'ils tournent, sans refaire d'export manuel à chaque analyse.

---

## Pourquoi cette fonctionnalité existe

Les deux moteurs peuvent tourner plusieurs heures ou plusieurs jours :

| Moteur | Backend | Frontend | Dossier runtime attendu |
|---|---:|---:|---|
| MAIN | `http://127.0.0.1:8000` | `5173` | `C:\Users\ilies\git\bitcoin-trading-assistant` |
| EXPERIMENTAL | `http://127.0.0.1:8001` | `5174` | `C:\Users\ilies\git\bitcoin-trading-v2-experiment` |

Jusqu'ici, l'analyse dépendait d'exports manuels. C'est fragile : si le run continue, si le code change, ou si un moteur est relancé, on perd la chronologie propre.

Le script `scripts/continuous_journal_exporter.py` règle ce problème :

- il exporte immédiatement les journaux des deux moteurs ;
- il recommence ensuite à intervalle régulier, par défaut toutes les heures ;
- il écrit les fichiers dans `docs/journaux/` ;
- il identifie clairement le moteur dans le nom du fichier ;
- il ajoute la branche et le commit Git dans le nom et dans le JSON ;
- il maintient aussi un flux `.jsonl` append-only par moteur et par signature de code ;
- il écrit un manifeste `live-export-manifest.json` pour retrouver le dernier snapshot.

---

## Commandes rapides

Depuis la racine du repo principal :

```powershell
# Export immédiat unique
.\scripts\start-journal-exporter.ps1 -Once

# Export continu toutes les heures
.\scripts\start-journal-exporter.ps1 -IntervalSeconds 3600

# Export continu dans une fenêtre PowerShell séparée
.\scripts\start-journal-exporter.ps1 -IntervalSeconds 3600 -Detached
```

Commande Python directe équivalente :

```powershell
python scripts/continuous_journal_exporter.py --once
python scripts/continuous_journal_exporter.py --interval-seconds 3600
```

---

## Fichiers produits

### Snapshots JSON individuels

Dossier :

```text
docs/journaux/live-snapshots/
```

Format :

```text
btc-trading-journal-YYYY-MM-DDTHH-MM-SSZ-MAIN-PORT5173-master-<sha>.json
btc-trading-journal-YYYY-MM-DDTHH-MM-SSZ-EXPERIMENTAL-PORT5174-experiment-v2-fees-and-1m-<sha>.json
```

Exemple :

```text
docs/journaux/live-snapshots/btc-trading-journal-2026-04-25T22-00-00Z-MAIN-PORT5173-master-2b781ac.json
```

### Flux append-only `.jsonl`

Dossier :

```text
docs/journaux/live-streams/
```

Format :

```text
btc-trading-journal-stream-MAIN-PORT5173-master-<sha>.jsonl
btc-trading-journal-stream-EXPERIMENTAL-PORT5174-experiment-v2-fees-and-1m-<sha>.jsonl
```

Chaque ligne contient :

- la métadonnée du snapshot ;
- un résumé utile ;
- le payload complet du journal.

Ce fichier permet de suivre l'évolution du run sans devoir ouvrir 50 fichiers séparés.

### Manifeste

Fichier :

```text
docs/journaux/live-export-manifest.json
```

Il pointe vers le dernier snapshot disponible par moteur et résume :

- nombre de trades ;
- PnL net ;
- frais cumulés ;
- écart éventuel entre `account.total_fees` et la somme des `trade.trading_fees` ;
- branche/commit ;
- statut OK/ERROR.

---

## Ce que le script ajoute dans chaque export

Chaque JSON exporté garde le contenu original de `/paper/journal/export`, puis ajoute :

```json
"_snapshot_meta": {
  "snapshot_id": "MAIN-2026-04-25T22-00-00Z",
  "captured_at": "2026-04-25T22:00:00+00:00",
  "engine": "MAIN",
  "backend_url": "http://127.0.0.1:8000",
  "frontend_port": 5173,
  "export_endpoint": "http://127.0.0.1:8000/paper/journal/export",
  "git": {
    "branch": "master",
    "sha": "2b781ac",
    "dirty": true,
    "repo_path": "C:\\Users\\ilies\\git\\bitcoin-trading-assistant"
  },
  "status": "ok"
}
```

Important : `dirty=true` est normal dès que des snapshots sont écrits localement dans `docs/journaux/`.

---

## Gestion des erreurs

Si un backend n'est pas joignable, le script n'échoue pas brutalement. Il écrit un fichier d'erreur dans :

```text
docs/journaux/live-errors/
```

Exemple :

```json
{
  "_snapshot_meta": {
    "engine": "EXPERIMENTAL",
    "status": "error"
  },
  "error": {
    "type": "URLError",
    "message": "[WinError 10061] Aucune connexion n'a pu être établie..."
  }
}
```

Cela permet de voir précisément quand un moteur était arrêté.

---

## Variables d'environnement utiles

| Variable | Rôle |
|---|---|
| `BTC_MAIN_BACKEND_URL` | Override URL backend MAIN |
| `BTC_EXPERIMENT_BACKEND_URL` | Override URL backend EXP |
| `BTC_EXPERIMENT_REPO` | Override chemin du worktree expérimental |

Exemple :

```powershell
$env:BTC_EXPERIMENT_REPO="C:\Users\ilies\git\bitcoin-trading-v2-experiment"
python scripts/continuous_journal_exporter.py --interval-seconds 3600
```

---

## Règle d'analyse

Pour une analyse fiable, utiliser en priorité :

1. `docs/journaux/live-export-manifest.json` pour savoir quel est le dernier export ;
2. le dernier snapshot individuel de chaque moteur ;
3. le `.jsonl` si on veut analyser l'évolution heure par heure ;
4. le commit Git présent dans `_snapshot_meta.git` pour savoir quel code a produit le run.

---

## Limite importante

Le script écrit les journaux sur la machine locale. Ils deviennent visibles depuis GitHub seulement après commit/push, ou s'ils sont envoyés/uploadés dans une conversation.

Ce point est volontaire : on ne veut pas que le script pousse automatiquement des fichiers de run toutes les heures sans contrôle.
