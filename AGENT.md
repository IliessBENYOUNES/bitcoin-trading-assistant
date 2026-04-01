# 🤖 Agent Rules — Bitcoin Trading Assistant

> Ce document définit les règles que tout agent IA (Copilot, GPT, Claude, etc.) doit suivre lorsqu'il travaille sur ce projet.

---

## Règle n°1 — TOUJOURS mettre à jour CURRENT_STATE.md avant commit & push

**Avant chaque commit et push**, l'agent DOIT :

1. **Lire** `docs/CURRENT_STATE.md`
2. **Mettre à jour** les sections impactées par les changements :
   - Version courante (si changée)
   - Dernier commit (hash + message)
   - Date de dernière mise à jour
   - Nombre de tests (si ajoutés/supprimés)
   - Fonctionnalités livrées (si ajoutées)
   - Architecture (si nouveaux fichiers/dossiers)
   - Ce qui n'est PAS encore fait (si une feature est complétée)
   - Problèmes connus (si résolus ou nouveaux)
3. **Inclure** le fichier CURRENT_STATE.md modifié dans le commit

> ⚠️ Un commit sans mise à jour de CURRENT_STATE.md est un commit incomplet.

---

## Règle n°2 — Lancer les tests avant de commit

Avant tout commit, l'agent doit :

```bash
cd backend
python -m pytest tests/ -v
```

Et vérifier :
- ✅ Tous les tests passent
- ✅ Aucun nouveau test en échec
- Si des tests échouent → corriger avant de commit

Pour le frontend :
```bash
cd frontend
npx tsc --noEmit
```

---

## Règle n°3 — Messages de commit conventionnels

Utiliser le format [Conventional Commits](https://www.conventionalcommits.org/) :

```
<type>(<scope>): <description courte>
```

Types autorisés :
- `feat` — nouvelle fonctionnalité
- `fix` — correction de bug
- `docs` — documentation uniquement
- `test` — ajout/modification de tests
- `refactor` — refactoring sans changement fonctionnel
- `chore` — maintenance (deps, config, cleanup)
- `style` — formatage, pas de changement de logique

Exemples :
```
feat(scheduler): add email notification on job failure
fix(frontend): fix chart crash on empty candles array
docs: update CURRENT_STATE.md
test(indicators): add edge case for SMA with NaN values
```

---

## Règle n°4 — Ne jamais casser l'existant

Avant de modifier du code existant :
1. **Lire** le fichier complet avant d'éditer
2. **Comprendre** le contexte (pourquoi ce code existe)
3. **Vérifier** les imports et dépendances
4. **Tester** après modification

Ne pas :
- ❌ Supprimer du code sans comprendre son rôle
- ❌ Changer des signatures de fonction sans vérifier les appelants
- ❌ Modifier la structure de la DB sans migration

---

## Règle n°5 — Respecter l'architecture existante

Le projet suit cette structure — la respecter :

```
backend/app/
├── api/routes/     → Endpoints FastAPI (routing uniquement)
├── services/       → Logique métier (calculs, appels externes)
├── models/         → Modèles SQLAlchemy (DB)
├── schemas/        → Schémas Pydantic (validation/sérialisation)
├── tasks/          → Jobs planifiés (scheduler)
└── utils/          → Utilitaires réutilisables
```

```
frontend/src/
├── pages/          → Pages (1 par route)
├── components/     → Composants réutilisables
├── hooks/          → Custom hooks React
├── api/            → Appels API typés
└── types/          → Types TypeScript partagés
```

---

## Règle n°6 — Documenter les décisions

Si un choix technique non trivial est fait, ajouter un commentaire expliquant **pourquoi** :

```python
# On utilise upsert au lieu de insert pour garantir l'idempotence
# du resample : relancer le job ne crée pas de doublons
```

---

## Règle n°7 — Pas de secrets dans le code

- ❌ Jamais de clés API, mots de passe ou tokens dans le code
- ✅ Utiliser les variables d'environnement via `.env` et `config.py`
- Le fichier `.env` est dans le `.gitignore`

---

## Règle n°8 — Consulter la roadmap avant d'implémenter

Avant d'ajouter une feature :
1. Lire `docs/ROADMAP.md` pour la phase courante
2. Lire `docs/ROADMAP_INFINI.md` pour la vision long terme
3. S'assurer que la feature s'inscrit dans la bonne phase

Ne pas implémenter une feature de la phase 6 si la phase 3 n'est pas terminée.

---

## Règle n°9 — Garder les dépendances à jour dans requirements.txt / package.json

Si une nouvelle dépendance Python est utilisée :
```
pip install <package>
pip freeze | grep <package> >> requirements.txt  # Avec version pinned
```

Si une nouvelle dépendance npm est utilisée :
```
npm install <package>  # Automatiquement ajouté à package.json
```

---

## Règle n°10 — Préférer la simplicité

- Un code simple et lisible > un code clever et compact
- Pas d'abstraction prématurée
- Pas de design pattern si un `if` suffit
- Le code le plus facile à maintenir est celui qu'on n'écrit pas

---

## Checklist pré-commit

```
[ ] Tests backend passent (110+ tests)
[ ] Frontend compile (tsc --noEmit)
[ ] docs/CURRENT_STATE.md mis à jour
[ ] Message de commit conventionnel
[ ] Pas de secrets dans le code
[ ] Pas de fichiers temporaires (.pyc, node_modules, .idea)
```

