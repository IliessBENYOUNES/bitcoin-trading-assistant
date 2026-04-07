# 🧪 Test Manuel — Paper Trading & Risk Management (via l'UI)

> **Objectif** : Valider de bout en bout la feature Paper Trading telle que l'utilisateur final la voit et l'utilise. **Aucune API directe — tout se fait via l'interface.**
>
> **Pré-requis** :
> - Backend démarré (`cd backend ; .\venv\Scripts\activate ; uvicorn app.main:app --reload --port 8000`)
> - Frontend démarré (`cd frontend ; npm run dev`)
> - Ouvrir **http://localhost:5173**
>
> **Navigation** : Aller sur l'onglet **💼 Trading** (raccourci clavier : **3**)

---

## 📋 Parcours de test

| # | Scénario | Durée |
|---|----------|-------|
| 1 | Premier lancement — Découverte du panel | ~2min |
| 2 | Configurer le Risk Management | ~3min |
| 3 | Activer le Paper Trading | ~1min |
| 4 | Exécuter des ticks et observer | ~5min |
| 5 | Gérer une position ouverte | ~3min |
| 6 | Lire les métriques de performance | ~2min |
| 7 | Utiliser le Kill Switch d'urgence | ~2min |
| 8 | Réinitialiser le compte | ~2min |
| 9 | Scénario complet de bout en bout | ~5min |
| 10 | Cas limites et robustesse | ~3min |
| **Total** | | **~28min** |

---

## 1. 🔍 Premier lancement — Découverte du panel

### Étapes

1. Ouvrir `http://localhost:5173`
2. Appuyer sur **3** (ou cliquer l'onglet **💼 Trading**)
3. Observer les deux panels côte à côte

### Panel gauche : **Gestion du Risque** ✅

- [ ] Un bouclier + titre "Gestion du Risque" est visible
- [ ] Un chip coloré affiche le niveau de risque : **🟢 Sûr**, **🟡 Attention**, **🔴 Danger** ou **🟣 Bloqué**
- [ ] Le bouton **Kill Switch** est visible (texte : "🛡️ Kill Switch (arrêt d'urgence)")
- [ ] Une barre de progression "Perte journalière" est affichée (0.00 / XXX.XX USD)
- [ ] Trois mini-cards affichent : **Stop-Loss** (ex: 5% fixed), **Take-Profit** (ex: 10%), **Position Max** (ex: 2,500 $)
- [ ] Un bouton crayon (✏️) est visible en haut à droite pour configurer
- [ ] Un bouton chevron (▼) permet d'agrandir/réduire les détails

### Panel droit : **Paper Trading** ✅

- [ ] Titre "📋 Paper Trading" visible
- [ ] Un chip affiche **ACTIF** (vert) ou **INACTIF** (gris)
- [ ] Un champ "Capital ($)" avec la valeur 10000 par défaut
- [ ] Si INACTIF : un bouton vert **"Activer"** est visible
- [ ] Si ACTIF : boutons **"Tick"**, **"Reset"**, **"Actualiser"** visibles
- [ ] En bas : "📖 Journal des trades (0)" avec le texte "Aucun trade clôturé pour le moment."

---

## 2. ⚙️ Configurer le Risk Management

### 2.1 Voir la config par défaut

1. Dans le panel **Gestion du Risque**, cliquer sur le **chevron (▼)** pour déplier

- [ ] Les détails apparaissent : Portefeuille, Limite perte/jour, Ratio R/R cible
- [ ] Valeurs par défaut : Portefeuille 10,000 USD, Limite 3% (300 USD), Ratio ~2.0:1

### 2.2 Modifier la configuration

1. Cliquer sur le bouton **crayon (✏️)** en haut à droite
2. Le formulaire de configuration apparaît avec :
   - Type Stop-Loss (sélecteur : Fixe, Trailing, ATR)
   - Stop-Loss % et Take-Profit % côte à côte
   - Position Max % et Perte Max/Jour % côte à côte
   - Portefeuille Total (USD)

- [ ] Tous les champs sont pré-remplis avec les valeurs courantes

3. Modifier les valeurs :
   - Stop-Loss : **3%**
   - Take-Profit : **8%**
   - Type : **Trailing (suiveur)**
   - Portefeuille : **50000**

4. Cliquer sur l'icône **disquette (💾)** pour sauvegarder

- [ ] Le formulaire se ferme
- [ ] Les mini-cards se mettent à jour : Stop-Loss affiche "3% (trailing)", Take-Profit "8%"
- [ ] La position max a changé (25% de 50000 = 12,500 $)
- [ ] La barre de perte journalière montre un nouveau max (3% de 50000 = 1,500 USD)

### 2.3 Annuler une modification

1. Cliquer sur le **crayon (✏️)** à nouveau
2. Changer le Stop-Loss à 20%
3. Cliquer sur l'icône **annuler (✕)**

- [ ] Le formulaire se ferme
- [ ] Les valeurs n'ont **pas** changé (toujours 3%)

### 2.4 Remettre la config par défaut

1. Ré-ouvrir l'édition (crayon), remettre :
   - Stop-Loss : **5%**, Type : **Fixe**
   - Take-Profit : **10%**
   - Portefeuille : **10000**
2. Sauvegarder

- [ ] La config est revenue aux défauts

---

## 3. ▶️ Activer le Paper Trading

### 3.1 Activer avec le capital par défaut

1. Dans le panel **Paper Trading**, vérifier que le capital est **10000**
2. Cliquer sur le bouton vert **"Activer"**

- [ ] Le chip passe de **INACTIF** → **ACTIF** (vert)
- [ ] Le bouton "Activer" disparaît
- [ ] Les boutons **"Tick"**, **"Reset"**, **"Actualiser"** apparaissent
- [ ] La grille de métriques s'affiche :
  - Capital : **$10,000**
  - PnL total : **+0.00 $**
  - PnL % : **+0.00%**
  - Trades : **0**
  - Win Rate : **0.0%**
  - Max DD : **0.0%**
  - Sharpe : **—**
  - Profit Factor : **0.00**
  - Buy & Hold : **+0.00%**

### 3.2 Activer avec un capital personnalisé

1. D'abord, cliquer **"Reset"** (confirmer le dialogue)
2. Changer le champ Capital à **25000**
3. Cliquer **"Activer"**

- [ ] Capital affiché : **$25,000**

---

## 4. ⚡ Exécuter des ticks et observer

> Le tick consulte le moteur de décision (signaux techniques + score composite) et le risk engine pour décider s'il ouvre, maintient ou ferme une position.

### 4.1 Premier tick

1. Cliquer sur le bouton **"Tick"**
2. Un spinner apparaît pendant l'exécution

- [ ] Le bouton redevient cliquable après quelques secondes
- [ ] Une alerte colorée apparaît sous les contrôles : **"Dernier tick : ..."**
  - 🟢 Verte si une position a été ouverte
  - 🟡 Orange si une position a été fermée
  - 🔵 Bleue si "hold" (pas d'action)
- [ ] Le prix BTC actuel s'affiche en haut (chip "BTC $XX,XXX")

### Cas A — Position ouverte (alerte verte)

Si le tick a ouvert une position :

- [ ] Un encadré bleu apparaît : **"Position LONG ouverte"** ou **"Position SHORT ouverte"**
- [ ] Icône directionnelle : 📈 (long) ou 📉 (short)
- [ ] Infos affichées :
  - **Entrée** : prix en dollars
  - **SL** : prix en rouge (inférieur à l'entrée pour un long)
  - **TP** : prix en vert (supérieur à l'entrée pour un long)
  - **Taille** : montant en dollars de la position
- [ ] En dessous : Score du moteur de décision + raison
- [ ] Le bouton **"Fermer position"** (orange) apparaît à côté de "Tick"
- [ ] La métrique "PnL latent" apparaît dans la grille (positif ou négatif)

### Cas B — Aucune action (alerte bleue)

- [ ] Message du type : "Pas de signal clair" ou "Action = attendre"
- [ ] Pas de position affichée
- [ ] Les métriques ne changent pas

### Cas C — Bloqué (alerte info)

- [ ] Message indiquant que le risk engine a bloqué le trade
- [ ] Pas de position ouverte

### 4.2 Ticks suivants

Cliquer **"Tick" 5 à 10 fois** de suite :

- [ ] Chaque tick met à jour l'alerte "Dernier tick"
- [ ] Si une position est ouverte, les ticks suivants peuvent :
  - **Maintenir** la position ("hold")
  - **Fermer** par Take-Profit (**✅ TP** vert dans le journal)
  - **Fermer** par Stop-Loss (**❌ SL** rouge dans le journal)
  - **Fermer** par changement de signal
- [ ] Après une fermeture, le prochain tick peut ouvrir une nouvelle position
- [ ] Les métriques se mettent à jour progressivement :
  - Trades : compteur augmente
  - PnL total : s'accumule
  - Win Rate : se calcule
- [ ] Le journal des trades se remplit avec les trades fermés

### 4.3 Observer le journal des trades

Après plusieurs ticks :

- [ ] Le titre passe à : "📖 Journal des trades (N)"
- [ ] Un tableau s'affiche avec les colonnes :
  - **Status** : chip coloré (✅ TP, ❌ SL, ⚠️ Signal, ⏰ Expiré, ✋ Manuel)
  - **Direction** : 📈 Long ou 📉 Short
  - **Entrée** : prix d'entrée en $
  - **Sortie** : prix de sortie en $
  - **PnL** : en $ (vert si positif, rouge si négatif)
  - **PnL %** : en % (coloré)
  - **Durée (h)** : temps de la position en heures
  - **Raison** : tooltip avec la raison de sortie
- [ ] Le tableau est scrollable si plus de trades que la hauteur ne peut afficher

---

## 5. ✋ Gérer une position ouverte

### 5.1 Fermer manuellement

> Pré-requis : avoir une position ouverte (via des ticks)

1. Avec une position ouverte visible (encadré bleu), cliquer sur **"Fermer position"** (bouton orange)
2. Un dialogue de confirmation apparaît : "Fermer la position ouverte ?"
3. Cliquer **OK**

- [ ] L'encadré bleu de la position disparaît
- [ ] Un nouveau trade apparaît dans le journal avec status **✋ Manuel**
- [ ] Le PnL du trade est calculé (entrée vs prix courant)
- [ ] Les métriques se mettent à jour (Trades, PnL, Win Rate)
- [ ] Le bouton "Fermer position" disparaît (plus de position)

### 5.2 Annuler la fermeture

1. Avec une position ouverte, cliquer **"Fermer position"**
2. Cliquer **Annuler** dans le dialogue

- [ ] La position reste ouverte (rien ne change)

---

## 6. 📊 Lire les métriques de performance

Après au moins 3-4 trades fermés, vérifier la grille de métriques :

- [ ] **Capital** : reflète le capital courant (initial ± PnL)
- [ ] **PnL total** : somme des gains/pertes (en $, avec signe + ou -)
- [ ] **PnL %** : pourcentage par rapport au capital initial
- [ ] **Trades** : nombre total de trades clôturés
- [ ] **Win Rate** : % de trades gagnants (vert si ≥50%, rouge sinon)
- [ ] **Max DD** : drawdown maximum en % (toujours en rouge, c'est le pire recul)
- [ ] **Sharpe** : ratio de Sharpe (— si pas assez de données, sinon un nombre)
- [ ] **Profit Factor** : gains bruts / pertes brutes (>1.0 = rentable)
- [ ] **Buy & Hold** : comparaison avec la stratégie "acheter et ne rien faire"
- [ ] **PnL latent** : PnL non réalisé de la position ouverte (si applicable)

### Cohérence des métriques

- [ ] Si Win Rate > 50% et Profit Factor > 1.0, le PnL total devrait être positif
- [ ] Le Max DD devrait être ≤ 100% (pas de valeur aberrante)
- [ ] Le nombre de trades dans la grille = nombre de lignes dans le journal

---

## 7. 🛑 Utiliser le Kill Switch d'urgence

### 7.1 Activer le Kill Switch

1. Dans le panel **Gestion du Risque** (à gauche)
2. Cliquer sur le bouton **"🛡️ Kill Switch (arrêt d'urgence)"**

- [ ] Le bouton devient **rouge plein** avec une animation pulsante
- [ ] Le texte change : **"⛔ KILL SWITCH ACTIF — Cliquer pour désactiver"**
- [ ] Une alerte rouge apparaît en dessous : "Activation manuelle depuis le dashboard"
- [ ] Le chip de risque passe à **🟣 Bloqué**
- [ ] Le texte des détails (si déplié) confirme l'état bloqué

### 7.2 Vérifier que le trading est bloqué

1. Aller dans le panel **Paper Trading** (à droite)
2. Cliquer sur **"Tick"**

- [ ] L'alerte "Dernier tick" affiche un message de type "blocked" ou "risk bloqué"
- [ ] **Aucune** nouvelle position n'est ouverte
- [ ] Si une position était déjà ouverte, elle **reste ouverte** (pas fermée par le kill switch)

### 7.3 Désactiver le Kill Switch

1. Cliquer de nouveau sur le bouton Kill Switch (rouge pulsant)

- [ ] Le bouton redevient **contour orange** (mode normal)
- [ ] Le texte revient : "🛡️ Kill Switch (arrêt d'urgence)"
- [ ] L'alerte rouge de raison disparaît
- [ ] Le chip de risque revient à **🟢 Sûr** (ou le niveau approprié)

### 7.4 Confirmer le retour à la normale

1. Cliquer **"Tick"** dans Paper Trading

- [ ] Le tick fonctionne normalement (peut ouvrir une position)

---

## 8. 🔄 Réinitialiser le compte

### 8.1 Reset complet

1. Avec des trades dans le journal et un PnL non-nul
2. Cliquer sur le bouton rouge **"Reset"**
3. Dialogue de confirmation : "Réinitialiser le compte paper ? Tous les trades seront supprimés."
4. Cliquer **OK**

- [ ] Le capital revient à la valeur du champ Capital (10000 par défaut)
- [ ] **Toutes les métriques repassent à zéro** :
  - PnL : 0
  - Trades : 0
  - Win Rate : 0%
  - Max DD : 0%
  - Sharpe : —
  - Profit Factor : 0.00
- [ ] Le journal des trades est **vidé** : "Aucun trade clôturé pour le moment."
- [ ] La position ouverte (si existante) est supprimée
- [ ] L'alerte "Dernier tick" est effacée

### 8.2 Annuler le Reset

1. Cliquer **"Reset"**
2. Cliquer **Annuler** dans le dialogue

- [ ] Rien ne change — les trades et métriques sont préservés

---

## 9. 🔁 Scénario complet de bout en bout

Ce scénario simule le parcours type d'un utilisateur :

### Étape 1 : Configuration initiale
1. Aller sur l'onglet **💼 Trading** (touche **3**)
2. Dans Risk, vérifier que le niveau est **🟢 Sûr**
3. Optionnel : modifier le SL à 3% et le TP à 6% (crayon → éditer → sauver)

- [ ] ✅ Config sauvegardée

### Étape 2 : Activation
4. Si Paper Trading est INACTIF, entrer un capital de **10000** et cliquer **"Activer"**

- [ ] ✅ Compte activé, métriques à zéro

### Étape 3 : Premier cycle de trading
5. Cliquer **"Tick"** — observer le résultat
6. Si position ouverte → cliquer **"Tick"** encore 2-3 fois pour voir si TP/SL est touché
7. Si "hold" → continuer de cliquer jusqu'à obtenir une position

- [ ] ✅ Au moins un trade ouvert puis fermé

### Étape 4 : Accumulation
8. Exécuter **10 ticks supplémentaires**
9. Observer :
   - Le journal des trades se remplit
   - Le capital fluctue
   - Les métriques se calculent

- [ ] ✅ Plusieurs trades dans le journal
- [ ] ✅ Win Rate et Profit Factor calculés

### Étape 5 : Fermeture manuelle
10. Si une position est ouverte, cliquer **"Fermer position"** → confirmer

- [ ] ✅ Trade fermé manuellement visible dans le journal (✋ Manuel)

### Étape 6 : Kill Switch
11. Activer le Kill Switch dans le panel Risk
12. Cliquer **"Tick"** → vérifier que c'est bloqué
13. Désactiver le Kill Switch

- [ ] ✅ Blocage confirmé puis retour à la normale

### Étape 7 : Vérification finale
14. Aller sur l'onglet **📊 Dashboard** (touche **1**) puis revenir sur **💼 Trading** (touche **3**)

- [ ] ✅ Toutes les données sont préservées (pas de perte en changeant d'onglet)
- [ ] ✅ Le journal, les métriques, la position — tout est intact

### Étape 8 : Nettoyage
15. Cliquer **"Reset"** → confirmer

- [ ] ✅ Tout est remis à zéro proprement

---

## 10. ⚠️ Cas limites et robustesse

### 10.1 Ticks rapides

Cliquer **"Tick" très vite** (5-6 clics rapides) :

- [ ] Le bouton se grise pendant l'exécution (pas de double-clic)
- [ ] Pas de crash ni d'erreur dans l'interface
- [ ] Maximum **1 position ouverte** à tout moment

### 10.2 Changement d'onglet pendant un tick

1. Cliquer **"Tick"**
2. Immédiatement passer à l'onglet **📊 Dashboard** (touche **1**)
3. Revenir sur **💼 Trading** (touche **3**)

- [ ] Les données sont à jour (le tick s'est bien exécuté)
- [ ] Pas de state corrompu

### 10.3 Fermer sans position ouverte

1. S'assurer qu'il n'y a pas de position ouverte

- [ ] Le bouton "Fermer position" n'est **pas visible** (il ne s'affiche que si une position est ouverte)
- [ ] Impossible de déclencher une fermeture sans position → pas de bouton, pas de crash

### 10.4 Reset avec position ouverte

1. Avoir une position ouverte (via tick)
2. Cliquer **"Reset"** → confirmer

- [ ] La position est supprimée avec le reste
- [ ] Le journal est vidé
- [ ] Pas d'erreur

### 10.5 Affichage avec 0 trade

Après un reset (aucun trade) :

- [ ] Win Rate : 0.0% (pas de "NaN" ou "Infinity")
- [ ] Sharpe : "—" (tiret, pas de nombre)
- [ ] Profit Factor : 0.00
- [ ] Max DD : 0.0%
- [ ] Journal : "Aucun trade clôturé pour le moment."

### 10.6 Responsive mobile

1. Réduire la largeur du navigateur (ou DevTools mode mobile)

- [ ] Les deux panels passent en **colonne** (un sous l'autre)
- [ ] La grille de métriques s'adapte
- [ ] Le journal reste scrollable
- [ ] Les boutons restent accessibles

---

## 11. ✅ Checklist récapitulative

| # | Test | Résultat |
|---|------|----------|
| **Découverte** | | |
| 1.1 | Panel Risk visible avec chip de risque | ☐ |
| 1.2 | Panel Paper Trading visible avec statut | ☐ |
| 1.3 | Kill Switch bouton visible | ☐ |
| 1.4 | Barre de perte journalière affichée | ☐ |
| **Configuration Risk** | | |
| 2.1 | Config par défaut lisible (déplier) | ☐ |
| 2.2 | Édition : formulaire s'ouvre et sauvegarde | ☐ |
| 2.3 | Annulation : retour aux valeurs précédentes | ☐ |
| **Activation Paper** | | |
| 3.1 | Activation avec capital par défaut | ☐ |
| 3.2 | Chip passe à ACTIF, métriques à zéro | ☐ |
| **Ticks** | | |
| 4.1 | Premier tick exécuté sans erreur | ☐ |
| 4.2 | Position ouverte affichée (si achat/vente) | ☐ |
| 4.3 | SL/TP/Taille/Direction cohérents | ☐ |
| 4.4 | Ticks multiples — pas de crash | ☐ |
| 4.5 | Fermeture auto (TP ou SL) visible dans journal | ☐ |
| 4.6 | Journal se remplit avec les trades | ☐ |
| **Position** | | |
| 5.1 | Fermeture manuelle fonctionne | ☐ |
| 5.2 | Trade "✋ Manuel" dans le journal | ☐ |
| 5.3 | Bouton "Fermer" absent quand pas de position | ☐ |
| **Métriques** | | |
| 6.1 | Capital mis à jour | ☐ |
| 6.2 | Win Rate cohérent | ☐ |
| 6.3 | PnL total = somme du journal | ☐ |
| 6.4 | Profit Factor et Sharpe affichés | ☐ |
| **Kill Switch** | | |
| 7.1 | Activation : bouton rouge pulsant | ☐ |
| 7.2 | Chip risque → 🟣 Bloqué | ☐ |
| 7.3 | Tick bloqué quand kill switch actif | ☐ |
| 7.4 | Désactivation : retour à la normale | ☐ |
| **Reset** | | |
| 8.1 | Reset remet tout à zéro | ☐ |
| 8.2 | Journal vidé après reset | ☐ |
| 8.3 | Annulation du reset préserve les données | ☐ |
| **Robustesse** | | |
| 10.1 | Ticks rapides — pas de double position | ☐ |
| 10.2 | Changement d'onglet — données préservées | ☐ |
| 10.3 | 0 trade — pas de NaN/crash | ☐ |
| 10.4 | Reset avec position ouverte | ☐ |
| 10.5 | Responsive mobile | ☐ |

---

## 12. 🕐 Temps total estimé

| Partie | Temps |
|--------|-------|
| Découverte + Config Risk | ~5 min |
| Activation + Ticks | ~6 min |
| Position + Fermeture | ~3 min |
| Métriques + Kill Switch | ~4 min |
| Reset + Robustesse | ~5 min |
| Scénario bout en bout | ~5 min |
| **Total** | **~28 min** |

---

## 13. ❓ FAQ Utilisateur

**Q: Le tick ne fait rien (toujours "hold") ?**
> C'est normal. Le moteur de décision analyse les signaux techniques réels. Si les conditions de marché ne donnent pas un signal clair, le système attend. Continuez de cliquer ou revenez plus tard quand le marché bouge.

**Q: Le PnL est toujours négatif ?**
> Le paper trading simule des conditions réelles. Les frais (spread, SL) peuvent générer des pertes. C'est justement le but : tester la stratégie AVANT de risquer de l'argent réel. Ajustez les paramètres SL/TP dans le Risk panel.

**Q: Je ne vois pas le bouton "Fermer position" ?**
> Ce bouton n'apparaît que quand une position est ouverte. Si aucune position n'est active, le bouton est masqué — c'est voulu.

**Q: Le Kill Switch est activé mais je ne l'ai pas touché ?**
> Le Kill Switch se déclenche automatiquement si la perte journalière dépasse la limite configurée. Vérifiez la barre "Perte journalière" dans le Risk panel. Désactivez-le manuellement pour reprendre.

**Q: Comment changer la stratégie (SL/TP) ?**
> Cliquez sur le crayon (✏️) dans le panel Risk à gauche. Modifiez les pourcentages et sauvegardez. Les nouvelles positions utiliseront ces paramètres.

---

> 📝 **Note** : Les résultats du paper trading dépendent des conditions réelles du marché BTC au moment du test. Le système utilise le prix live via WebSocket et les signaux techniques calculés sur les données historiques. Chaque session de test donnera des résultats différents — c'est normal et attendu.
