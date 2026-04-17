# Guide de lancement des serveurs — Bitcoin Trading Assistant

> **2 instances** tournent en parallèle : **MAIN** (master) et **EXPERIMENTAL** (experiment/v2-fees-and-1m).
> Ce guide permet à n'importe quel agent ou humain de tout relancer proprement.

---

## Architecture des 2 instances

| Instance | Branche | Dossier | Backend | Frontend | Base de données |
|----------|---------|---------|---------|----------|-----------------|
| **MAIN** | `master` | `C:\Users\ilies\git\bitcoin-trading-assistant` | `http://localhost:8000` | `http://localhost:5173` | `bitcoin_assistant` (PostgreSQL) |
| **EXPERIMENTAL** | `experiment/v2-fees-and-1m` | `C:\Users\ilies\git\bitcoin-trading-v2-experiment` | `http://localhost:8001` | `http://localhost:5174` | `bitcoin_experiment` (PostgreSQL) |

> Le dossier expérimental est un **git worktree** du repo principal, pas un clone séparé.

---

## Lancer les 4 serveurs

### Ordre recommandé : backends d'abord, puis frontends.

### 1. Backend MAIN (port 8000)

```bash
cd /c/Users/ilies/git/bitcoin-trading-assistant/backend
source venv/Scripts/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1 &
```

### 2. Backend EXPERIMENTAL (port 8001)

```bash
cd /c/Users/ilies/git/bitcoin-trading-v2-experiment/backend
source venv/Scripts/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001 2>&1 &
```

### 3. Frontend MAIN (port 5173)

```bash
cd /c/Users/ilies/git/bitcoin-trading-assistant/frontend
npx vite --host 127.0.0.1 --port 5173 2>&1 &
```

### 4. Frontend EXPERIMENTAL (port 5174)

```bash
cd /c/Users/ilies/git/bitcoin-trading-v2-experiment/frontend
npx vite --host 127.0.0.1 --port 5174 2>&1 &
```

---

## Vérifier que tout fonctionne

```bash
# Vérifier les 4 ports
netstat -ano | grep -E "LISTENING" | grep -E ":(8000|8001|5173|5174) "

# Health check backends
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8001/health

# Les deux doivent retourner : {"status":"healthy","service":"bitcoin-trading-assistant"}
```

---

## Arrêter les serveurs

```bash
# Trouver les PID
netstat -ano | grep -E "LISTENING" | grep -E ":(8000|8001|5173|5174) "

# Tuer par PID (remplacer XXXX par le PID)
taskkill //F //PID XXXX

# OU tuer tout d'un coup
taskkill //F //IM uvicorn.exe 2>/dev/null
taskkill //F //IM node.exe 2>/dev/null   # Attention : tue TOUS les processus node
```

---

## Mapping des ports (ne pas confondre !)

```
MAIN :          Backend 8000  ←→  Frontend 5173
EXPERIMENTAL :  Backend 8001  ←→  Frontend 5174
```

---

## Fichiers de config clés

| Fichier | Instance | Rôle |
|---------|----------|------|
| `bitcoin-trading-assistant/backend/.env` | MAIN | DB `bitcoin_assistant`, pas de port (défaut 8000) |
| `bitcoin-trading-v2-experiment/backend/.env` | EXP | DB `bitcoin_experiment`, port passé en CLI |
| `bitcoin-trading-assistant/frontend/.env` | MAIN | `VITE_API_BASE_URL=http://localhost:8000` |
| `bitcoin-trading-v2-experiment/frontend/.env` | EXP | `VITE_API_BASE_URL=http://localhost:8001` |
| `bitcoin-trading-assistant/frontend/vite.config.ts` | MAIN | Port 5173, proxy → 8000 |
| `bitcoin-trading-v2-experiment/frontend/vite.config.ts` | EXP | Port 5174, proxy → 8001 |

---

## Prérequis

- **PostgreSQL** doit tourner avec les 2 bases créées : `bitcoin_assistant` et `bitcoin_experiment`
- **User PostgreSQL** : `btc_user` / `btc_password_123`
- **Python venv** : chaque backend a son propre `venv/` dans son dossier
- **Node modules** : chaque frontend a son propre `node_modules/`

---

## Erreurs fréquentes

| Symptôme | Cause | Solution |
|----------|-------|----------|
| `Connection refused` sur 8001 | Backend exp pas lancé | Relancer la commande 2 ci-dessus |
| Frontend exp affiche données du main | Proxy vite.config pointe vers 8000 au lieu de 8001 | Vérifier `vite.config.ts` exp : target doit être `http://localhost:8001` |
| Port déjà utilisé | Serveur précédent pas arrêté | `netstat -ano | grep :PORT` puis `taskkill //F //PID` |
| Backend démarre mais pas de données | DB vide | Vérifier la DB PostgreSQL correspondante |
| Les deux frontends sur le même port | vite.config.ts exp a port 5173 | Doit être 5174 |
