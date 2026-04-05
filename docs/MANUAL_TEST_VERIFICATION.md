# 🧪 Plan de Test Manuel — Vérification Historique (v1.2.2)

> **Objectif** : Valider de bout en bout la fonctionnalité de vérification historique
> (chargement de données, intégrité, vérification ponctuelle, walk-forward, mode comparaison).
>
> **Pré-requis** : Backend démarré sur `http://localhost:8000`, Frontend sur `http://localhost:5173`

---

## 📋 Sommaire

| # | Section | Durée estimée |
|---|---------|---------------|
| 1 | Chargement historique BTC | ~30s |
| 2 | Vérification intégrité des données | ~10s |
| 3 | Chargement sentiment historique (Fear & Greed) | ~10s |
| 4 | Vérification ponctuelle (Time-Travel) | ~5s |
| 5 | Analyse Walk-Forward | ~2-5min |
| 6 | Mode comparaison (Technique vs Technique+Sentiment) | ~5-10min |
| 7 | Tests API directs (Swagger) | ~5min |
| 8 | Cas d'erreur et edge cases | ~5min |

---

## 1. 📥 Chargement historique BTC

### Via le Frontend (Dashboard)

1. Ouvrir `http://localhost:5173`
2. Scroller jusqu'au panel **"🕰️ Vérification Historique"** (card violette)
3. Sélectionner le timeframe **1d** (par défaut) dans le sélecteur "TF"
4. Cliquer sur le bouton **"Charger depuis 2017"**

### Résultat attendu ✅

- [ ] Une barre de progression s'affiche pendant le chargement
- [ ] Un message de succès apparaît : `✅ XXXX candles chargées en X.Xs`
- [ ] Le nombre de candles devrait être **~2800+** (de 2017-08-17 à aujourd'hui)
- [ ] L'affichage de la plage de dates se met à jour : `2017-08-17 → 2026-04-XX`
- [ ] Le chip en haut à droite affiche le nombre de candles (ex: `2,850 candles`)

### Relancer le chargement (idempotence)

5. Cliquer à nouveau sur **"Charger depuis 2017"**

- [ ] Le chargement est rapide (pas de doublons créés)
- [ ] Le nombre de candles reste stable (idempotence confirmée)

### Test avec timeframe 4h

6. Changer le TF à **4h**
7. Cliquer sur **"Charger depuis 2017"**

- [ ] ~19000+ candles chargées
- [ ] Le chargement prend plus de temps (~30s)

---

## 2. 🔍 Vérification intégrité des données

> L'intégrité s'affiche automatiquement après le chargement.

### Résultat attendu ✅

- [ ] Le bloc **"Intégrité des données"** s'affiche sous la section chargement
- [ ] Un grade de qualité est affiché : **EXCELLENT**, **GOOD**, **WARNING** ou **CRITICAL**
- [ ] Le pourcentage de complétude est affiché (ex: `99.8%`)
- [ ] Le nombre `X / Y candles attendues` est cohérent
- [ ] Si des gaps existent, des chips orange les listent (ex: `2020-01-05 → 2020-01-06 (1j)`)
- [ ] Un texte descriptif est affiché en bas

### Critères de qualité

| Grade | Complétude | Couleur |
|-------|-----------|---------|
| EXCELLENT | ≥ 99% | 🟢 Vert |
| GOOD | ≥ 97% | 🟢 Vert clair |
| WARNING | ≥ 95% | 🟡 Orange |
| CRITICAL | < 95% | 🔴 Rouge |

---

## 3. 🧠 Chargement sentiment historique (Fear & Greed)

1. Cliquer sur le bouton **"Charger Fear & Greed (sentiment)"**

### Résultat attendu ✅

- [ ] Un message de succès apparaît : `✅ Sentiment: XXXX points récupérés, X insérés, X mis à jour (X.Xs)`
- [ ] ~2900 points de données sont chargés
- [ ] Les infos de plage s'affichent : `2,900 points • 2018-02-01 → 2026-04-XX`
- [ ] Le message d'info en haut change de ⚠️ à ✅ : `Sentiment historique disponible`

### Relancer (idempotence)

2. Cliquer à nouveau sur le bouton

- [ ] `0 insérés, XXXX mis à jour` — pas de doublons

---

## 4. 🔎 Vérification ponctuelle (Time-Travel)

### Test 1 : Date connue (crash COVID — mars 2020)

1. Dans la section **"2. Vérifier à une date"**
2. Sélectionner la date **2020-03-01** dans le date picker
3. Cliquer sur **"Vérifier"**

### Résultat attendu ✅

- [ ] La prédiction s'affiche avec :
  - Le prix BTC à cette date (autour de $8,500-$8,800)
  - Un chip d'action : **ACHETER**, **VENDRE** ou **ATTENDRE**
  - Un score composite (ex: `+15` ou `-8`)
  - Le scénario dominant avec probabilité
  - Un résumé texte de la décision
- [ ] La section **"Comparaison avec la réalité"** s'ouvre et montre :
  - **+7j** : variation réelle, direction, ✅ ou ❌, score qualité Q
  - **+30j** : idem (COVID → probablement grosse baisse)
  - **+90j** : idem (recovery post-COVID)
- [ ] Chaque horizon affiche un score qualité Q (0-100)
- [ ] Si direction correcte, un badge "↕ DIR" vert s'affiche

### Test 2 : Date en bull run (fin 2020)

4. Sélectionner **2020-11-01**
5. Cliquer sur **"Vérifier"**

- [ ] Prix autour de $13,000-$14,000
- [ ] Si le modèle recommande "acheter" → à +90j le BTC était à ~$50k → ✅ correct
- [ ] Score qualité élevé pour les bonnes prédictions

### Test 3 : Date récente (2024)

6. Sélectionner **2024-01-15**
7. Cliquer sur **"Vérifier"**

- [ ] Résultat cohérent avec données récentes
- [ ] Tous les horizons ont des données (pas d'erreur)

### Test 4 : Date trop ancienne (pas de données)

8. Sélectionner **2015-01-01**
9. Cliquer sur **"Vérifier"**

- [ ] Message d'alerte orange : `Aucune donnée disponible à cette date`

---

## 5. 📊 Analyse Walk-Forward

### Test rapide (petite plage)

1. Dans la section **"3. Analyse Walk-Forward"**
2. Configurer :
   - **Début** : `2020-01-01`
   - **Fin** : `2021-01-01`
   - **Pas** : `30` jours
3. Décocher "Mode comparaison"
4. Cliquer sur **"Lancer"**

### Résultat attendu ✅

- [ ] Barre de progression pendant l'analyse (~30s-1min)
- [ ] Message texte résumé de l'analyse (fond orange)
- [ ] **3 barres d'accuracy** : une par horizon (7j, 30j, 90j)
  - Barre verte si ≥60%, orange si ≥40%, rouge sinon
  - Affiche `X/Y` correct
- [ ] **Score qualité global** : chip coloré `Qualité globale: XX/100`
- [ ] **Métriques par horizon** :
  - `Dir XX%` — Accuracy directionnelle
  - `Q XX` — Qualité moyenne
  - `HC XX%` — High confidence accuracy (si signaux forts)
  - `💰 XX%` — Profitabilité
- [ ] **Distribution des signaux** : nombre d'achats, ventes, attentes par horizon
- [ ] **Métadonnées** : nombre de points, durée en secondes
- [ ] **"Détail par date"** : section collapsible avec chaque point de vérification

### Ouvrir le détail

5. Cliquer sur **"Détail par date (XX)"** pour déplier

- [ ] Liste scrollable de toutes les dates testées
- [ ] Chaque ligne montre : date, action, score, et 3 chips ✅/❌ par horizon

---

## 6. ⚖️ Mode Comparaison (Technique seul vs Technique + Sentiment)

> **Pré-requis** : Avoir chargé le sentiment historique (étape 3)

### Lancer

1. Configurer le walk-forward :
   - **Début** : `2020-01-01`
   - **Fin** : `2024-01-01`
   - **Pas** : `60` jours
2. **Cocher** ✅ "Mode comparaison (technique seul vs technique + sentiment)"
3. Cliquer sur **"Lancer"**

### Résultat attendu ✅

- [ ] L'analyse prend environ **2x plus longtemps** (car deux passes)
- [ ] En plus des résultats normaux, un bloc **"Comparaison : Technique seul vs Technique + Sentiment"** apparaît

### Bloc comparaison

- [ ] **Verdict** : une alerte colorée (verte/orange/bleue) avec le texte du verdict
  - Ex: `Le sentiment améliore la précision de +3.5%` ou `Aucun apport significatif`
- [ ] **Deux colonnes côte à côte** :
  - **📊 Technique seul** : Accuracy, Qualité, Direction, Profitable
  - **🧠 Technique + Sentiment** : mêmes métriques
- [ ] **Chips delta** :
  - `Δ Accuracy : +X.X%` — vert si positif, rouge si négatif
  - `Δ Qualité : +X.X` — idem

### Interprétation

| Delta Accuracy | Verdict attendu |
|---------------|-----------------|
| > +2% | 🟢 Le sentiment améliore les prédictions |
| -2% à +2% | 🔵 Pas de différence significative |
| < -2% | 🟡 Le sentiment dégrade les prédictions |

---

## 7. 🛠️ Tests API directs (Swagger)

Ouvrir `http://localhost:8000/docs` (Swagger UI).

### 7.1 GET `/backtest/history/range`

```
GET /backtest/history/range?symbol=BTC/USD&timeframe=1d
```

- [ ] Retourne `has_data: true`, `min_date`, `max_date`, `total_candles`

### 7.2 GET `/backtest/history/integrity`

```
GET /backtest/history/integrity?symbol=BTC/USD&timeframe=1d
```

- [ ] Retourne `quality_grade`, `completeness_pct`, `gaps`, `total_candles`, `expected_candles`

### 7.3 POST `/backtest/verify`

```json
{
  "target_date": "2021-01-01",
  "symbol": "BTC/USD",
  "timeframe": "1d",
  "history_days": 200,
  "horizons": [7, 30, 90]
}
```

- [ ] Retourne `predicted_action`, `predicted_score`, `outcomes` avec 3 horizons
- [ ] Chaque outcome a `correct`, `quality_score`, `directional_match`

### 7.4 POST `/backtest/walk-forward`

```json
{
  "start_date": "2022-01-01",
  "end_date": "2023-01-01",
  "step_days": 30,
  "symbol": "BTC/USD",
  "timeframe": "1d",
  "history_days": 200,
  "horizons": [7, 30],
  "compare_mode": false
}
```

- [ ] Retourne `total_points`, `accuracy_by_horizon`, `points`, `summary`, `overall_quality_score`
- [ ] `accuracy_by_horizon` contient les métriques avancées (directional, quality, high_confidence, profitable)

### 7.5 POST `/backtest/walk-forward` avec compare_mode

```json
{
  "start_date": "2022-01-01",
  "end_date": "2023-01-01",
  "step_days": 60,
  "compare_mode": true
}
```

- [ ] `comparison` n'est PAS null
- [ ] `comparison.technical_only` et `comparison.with_sentiment` sont remplis
- [ ] `comparison.verdict` contient un texte lisible

### 7.6 POST `/sentiment/history/load`

```json
{}
```

- [ ] Retourne `fetched`, `inserted`, `updated`, `duration_seconds`

### 7.7 GET `/sentiment/history/range`

```
GET /sentiment/history/range
```

- [ ] Retourne `has_data: true`, `min_date`, `max_date`, `total_points`

### 7.8 GET `/sentiment/history/at-date?date=2021-06-15`

- [ ] Retourne le score Fear & Greed à cette date (ou le plus proche)

---

## 8. ⚠️ Cas d'erreur et edge cases

### 8.1 Vérifier sans données chargées

1. (Si base vide) Essayer de cliquer "Vérifier" sans avoir chargé l'historique

- [ ] Bouton désactivé (grisé) si `has_data = false`
- [ ] Ou message d'erreur explicite

### 8.2 Date hors plage

1. Charger l'historique (2017→now)
2. Essayer de vérifier à la date **2017-01-01** (avant les données Binance)

- [ ] Le backend retourne une erreur 422 ou un résultat vide
- [ ] Le frontend affiche un message d'erreur lisible

### 8.3 Date future

1. Sélectionner une date dans le futur (ex: `2027-01-01`)
2. Cliquer "Vérifier"

- [ ] Erreur gérée proprement (pas de crash)

### 8.4 Walk-forward avec plage invalide

1. Mettre `Début = 2025-01-01`, `Fin = 2020-01-01` (inversé)
2. Cliquer "Lancer"

- [ ] Erreur 422 ou message d'erreur

### 8.5 Walk-forward avec pas trop grand

1. Configurer `Début = 2020-01-01`, `Fin = 2020-06-01`, `Pas = 365`
2. Lancer

- [ ] Résultat avec très peu de points (1-2), pas de crash

### 8.6 Relancer pendant un chargement

1. Lancer un walk-forward
2. Pendant qu'il tourne, essayer de cliquer à nouveau

- [ ] Le bouton est désactivé (grisé) pendant l'analyse
- [ ] Pas de double exécution

---

## 9. ✅ Checklist récapitulative

| # | Test | Résultat |
|---|------|----------|
| 1.1 | Chargement historique 1d (~2800 candles) | ☐ |
| 1.2 | Chargement idempotent (pas de doublons) | ☐ |
| 1.3 | Chargement historique 4h (~19000 candles) | ☐ |
| 2.1 | Intégrité affichée avec grade et % | ☐ |
| 2.2 | Gaps détectés et listés (si existants) | ☐ |
| 3.1 | Chargement Fear & Greed (~2900 points) | ☐ |
| 3.2 | Chargement sentiment idempotent | ☐ |
| 4.1 | Vérification ponctuelle — crash COVID (2020-03) | ☐ |
| 4.2 | Vérification ponctuelle — bull run (2020-11) | ☐ |
| 4.3 | Vérification ponctuelle — date récente (2024) | ☐ |
| 4.4 | Vérification — date sans données | ☐ |
| 5.1 | Walk-forward rapide (1 an, pas 30j) | ☐ |
| 5.2 | Accuracy bars + métriques affichées | ☐ |
| 5.3 | Détail par date dépliable | ☐ |
| 6.1 | Mode comparaison activé | ☐ |
| 6.2 | Verdict technique vs sentiment | ☐ |
| 6.3 | Colonnes côte à côte + deltas | ☐ |
| 7.1 | API /history/range fonctionne | ☐ |
| 7.2 | API /history/integrity fonctionne | ☐ |
| 7.3 | API /verify fonctionne | ☐ |
| 7.4 | API /walk-forward fonctionne | ☐ |
| 7.5 | API /walk-forward compare_mode | ☐ |
| 7.6 | API /sentiment/history/load | ☐ |
| 7.7 | API /sentiment/history/range | ☐ |
| 7.8 | API /sentiment/history/at-date | ☐ |
| 8.1 | Vérifier sans données → bouton désactivé | ☐ |
| 8.2 | Date hors plage → erreur propre | ☐ |
| 8.3 | Date future → erreur propre | ☐ |
| 8.4 | Plage inversée → erreur propre | ☐ |
| 8.5 | Pas trop grand → peu de points, pas de crash | ☐ |
| 8.6 | Double-clic pendant analyse → bouton désactivé | ☐ |

---

## 10. 🕐 Temps total estimé

| Partie | Temps |
|--------|-------|
| Chargement des données (BTC + sentiment) | ~1-2 min |
| Vérifications ponctuelles (4 tests) | ~1 min |
| Walk-forward (sans comparaison) | ~2-5 min |
| Walk-forward (avec comparaison) | ~5-10 min |
| Tests API Swagger | ~5 min |
| Cas d'erreur | ~5 min |
| **Total** | **~20-30 min** |

---

> 📝 **Note** : Les résultats d'accuracy du modèle varient selon les données réelles du marché.
> Un score de 50-60% sur les horizons courts (7j) et 55-65% sur les horizons longs (90j)
> est considéré comme correct pour un modèle basé sur l'analyse technique seule.

