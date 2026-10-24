# CAC 40 – Palmarès & agenda des résultats

Tableau de bord (Streamlit) qui affiche :

1. **Palmarès** : le top 10 et le flop 10 du CAC 40 sur la période choisie
   (1 jour, 5 jours, 1 mois, 3 mois, 6 mois, depuis le 1er janvier, 1 an), avec la
   performance de l'indice, le classement complet des 40 valeurs et la performance
   moyenne par secteur.
2. **Agenda des résultats** : les publications à venir, avec pour chaque société sa
   performance récente et l'amplitude moyenne de ses réactions passées (pour repérer
   les publications à risque), ainsi que les publications récentes et la réaction du
   marché.
3. **Impact des résultats** : pour chaque valeur, la réaction du cours à ses
   publications sur environ 4 ans (variation le jour J, surperformance par rapport au
   CAC 40, dérive sur 5 séances, surprise sur le BPA) et un graphique du cours avec les
   publications passées et à venir.

## Installation et lancement

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

L'application s'ouvre dans le navigateur (http://localhost:8501). Les cours sont mis
en cache 15 minutes et l'agenda 6 heures ; le bouton « Rafraîchir les données »
force une mise à jour.

## Application mobile

Le dossier `mobile/` contient une application web installable (PWA) adaptée au
téléphone, avec trois écrans :

- **Palmarès** : top 10 / flop 10 en graphique, avec un choix de période (1J à 1A) ;
- **Graphique** : courbe de cours de chaque valeur, losanges verts ou rouges aux dates
  de résultats (réaction du jour J) et comparaison possible avec le CAC 40 en base 100 ;
- **Agenda** : prochaines publications, jour par jour.

Elle est hébergée gratuitement sur **GitHub Pages**. Le workflow
`.github/workflows/mobile.yml` récupère les données toutes les 30 minutes pendant la
séance, puis publie le site. Aucun serveur n'est nécessaire.

### Mise en route (une seule fois)

1. Fusionner la pull request dans `main`.
2. Dans GitHub : **Settings → Pages → Build and deployment → Source : « GitHub Actions »**.
3. Onglet **Actions** → « Application mobile » → **Run workflow** (première publication).
4. Ouvrir `https://vuthypin.github.io/Logo/` sur le téléphone, puis :
   - **iPhone (Safari)** : bouton Partager → « Sur l'écran d'accueil » ;
   - **Android (Chrome)** : menu ⋮ → « Installer l'application ».

L'icône « CAC 40 » apparaît alors sur l'écran d'accueil et l'application s'ouvre en
plein écran. Les dernières données restent consultables hors connexion.

Pour tester l'application en local :

```bash
python scripts/export_data.py mobile/data.json
python -m http.server -d mobile 8000   # puis http://localhost:8000
```

## Données

- **Cours** : Yahoo Finance via `yfinance`, cours ajustés des dividendes. Les cours
  peuvent avoir environ 15 minutes de retard en séance.
- **Dates de résultats** : Yahoo Finance (page « earnings calendar » et calendrier de
  chaque valeur). Pour les sociétés européennes, la couverture de Yahoo n'est pas
  toujours complète. Vous pouvez donc ajouter ou corriger des dates dans
  `cac40_app/agenda_manuel.csv`. Ces dates sont prioritaires sur celles de Yahoo pour
  le même jour :

  ```csv
  ticker,date,timing,label
  MC.PA,2027-01-27,apres_cloture,Résultats annuels 2026
  TTE.PA,2027-02-11,avant_ouverture,Résultats T4
  ```

  `timing` vaut `avant_ouverture` ou `apres_cloture`. Il détermine la séance qui sert
  à mesurer la réaction.
- **Composition de l'indice** : `cac40_app/constituents.csv` (dernier changement :
  Eiffage a remplacé Edenred le 22/12/2025). Mettez ce fichier à jour après chaque
  révision trimestrielle d'Euronext.

## Méthode de calcul de la réaction aux résultats

- Publication **avant l'ouverture** (cas le plus fréquent à Paris) : clôture du jour J
  comparée à la clôture de la veille.
- Publication **après la clôture** : clôture du lendemain comparée à la clôture du
  jour J.
- **Surperformance** : réaction du titre moins la variation du CAC 40 sur la même
  séance.

## Tests

```bash
pip install pytest
python -m pytest
```

*Données indicatives, sans valeur de conseil en investissement.*
