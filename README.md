# Partage de frais

Application du projet 1 de l'UMONS : noter les dépenses d'un séjour entre amis et connaître le solde de chaque membre.

Le projet complète le squelette du professeur dans **`code-streamlit`**, avec les quatre tables SQLite et les exemples fournis. Le dossier `code-flask` est conservé comme référence ; la version développée et testée est celle de Streamlit.

Technologies : **Python 3.11 ou plus, SQLite, Streamlit, pytest et Git**. Aucun service externe n'est nécessaire pour utiliser l'application après installation.

## Installer sur macOS

Depuis le dossier local du dépôt :

```bash
cd /Users/Apple/Desktop/codelab-sans-agent
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r code-streamlit/requirements.txt
```

Pour une nouvelle copie sur une autre machine, récupérer d'abord le dépôt avec `git clone https://github.com/mghiii/codelab-sans-agent.git`, puis adapter la commande `cd` à son emplacement.

## Lancer l'application

Depuis la racine du dépôt, avec l'environnement activé :

```bash
python -m streamlit run code-streamlit/app.py --server.address=127.0.0.1
```

Ouvrir [l'application locale](http://127.0.0.1:8501). Pour arrêter le serveur, utiliser `Ctrl+C` dans le terminal.

Lors des lancements suivants :

```bash
cd /Users/Apple/Desktop/codelab-sans-agent
source .venv/bin/activate
python -m streamlit run code-streamlit/app.py --server.address=127.0.0.1
```

## Utiliser l'application

La barre latérale permet de sélectionner le groupe actif et de naviguer entre trois pages :

1. **Groupes** : créer un séjour avec ses dates et plusieurs membres, consulter les groupes existants et ajouter un membre au groupe actif. Un groupe peut être créé sans membre, puis complété.
2. **Dépenses** : saisir un libellé, un montant en euros, une date, un payeur et des participants. Ouvrir une dépense pour consulter les parts individuelles, la modifier ou la supprimer. Les filtres portent sur le membre concerné et la période. Le bouton CSV exporte les dépenses affichées.
3. **Soldes** : consulter, pour chaque membre, le total payé, les parts dues et le solde. Un montant positif est à recevoir ; un montant négatif est à rembourser.

Les montants acceptent la virgule ou le point (`10,50` ou `10.50`). Sélectionner les participants **dans l'ordre souhaité** : cet ordre est enregistré et affiché dans les détails. Le payeur peut être absent des participants.

Le filtre de membre retient les dépenses qu'il a payées **ou** auxquelles il participe. Les bornes de la période sont incluses. Le CSV utilise le séparateur `;`, la virgule décimale et l'encodage UTF-8 avec BOM pour conserver les accents dans un tableur.

## Règles de calcul et validations

Les règles sont vérifiées dans `gestion.py`, même si les fonctions sont appelées sans l'interface :

- Le nom du groupe, le nom d'un membre et le libellé d'une dépense ne peuvent pas être vides. Les noms des membres d'un groupe sont distincts, sans tenir compte des majuscules.
- La fin du séjour ne peut pas précéder son début.
- Le montant d'une dépense est strictement positif et ne contient aucune fraction de centime. Les montants trop grands pour un entier SQLite sont refusés.
- Il faut au moins un participant, sans doublon. Le payeur et tous les participants appartiennent au groupe.
- La date de la dépense est comprise entre le début et la fin du séjour, bornes incluses.
- Chaque montant est stocké et calculé en **centimes entiers**. La saisie en euros est convertie avec `Decimal`, sans arrondi silencieux.
- La division entière donne une part de base ; **tout le reste revient à la part due par le premier participant ajouté**. Par exemple, 5 centimes pour trois personnes donnent 3, 1 et 1 centimes.
- **Solde = total payé − total des parts dues**. La somme des parts vaut le montant de la dépense et la somme des soldes vaut zéro.

Chaque exemple ci-dessous concerne un groupe sans autre dépense, avec les participants dans l'ordre Alice, Bob, Chloé :

| Dépense payée par Alice | Alice | Bob | Chloé |
|---|---:|---:|---:|
| 30,00 € pour les trois | +20,00 € | −10,00 € | −10,00 € |
| 10,00 € pour les trois | +6,66 € | −3,33 € | −3,33 € |
| 10,00 € pour Bob et Chloé | +10,00 € | −5,00 € | −5,00 € |

La création, la modification et la suppression utilisent des transactions SQLite. Si une écriture échoue, les écritures de la même opération sont annulées. Les soldes sont recalculés à partir des dépenses enregistrées à chaque affichage.

## Base de données

`data.db`, à la racine du dépôt, est créé automatiquement. Les exemples du professeur sont conservés : le groupe **Vacances à Spa**, Alice, Bob et Chloé, ainsi que les courses de 30 €.

| Table | Colonnes |
|---|---|
| `groupes` | `id`, `nom`, `date_debut`, `date_fin` |
| `membres` | `id`, `groupe_id`, `nom` |
| `depenses` | `id`, `groupe_id`, `libelle`, `montant_centimes`, `date`, `payeur_id` |
| `participants` | `depense_id`, `membre_id`, **`ordre`** |

La seule extension du schéma est `participants.ordre`, à partir de zéro, avec un index unique sur `(depense_id, ordre)`. Les clés étrangères sont activées sur chaque connexion ; la suppression d'une dépense supprime aussi ses participations.

**Une ancienne base est migrée automatiquement, sans effacer ses données.** L'ordre des anciennes participations est repris à partir des `rowid` existants, qui correspondent à leur ordre d'insertion dans le schéma fourni. Si cet ordre historique a déjà été perdu par une reconstruction externe de la table, il ne peut pas être reconstitué avec certitude. La migration peut être relancée sans dupliquer les exemples. Il n'est pas nécessaire de supprimer `data.db` pour cette mise à jour.

Pour utiliser un autre fichier, définir `PARTAGE_FRAIS_DB` avant le lancement. Le dossier parent de ce fichier doit exister.

## Exécuter les tests

Depuis la racine du dépôt, avec l'environnement activé :

```bash
python -m pytest -q
```

`pytest.ini` sélectionne uniquement la version Streamlit, pour éviter les conflits de noms avec le squelette Flask. Chaque test utilise une base SQLite temporaire grâce à `tmp_path` et à `PARTAGE_FRAIS_DB`, y compris les tests de l'interface avec `AppTest`. **Les tests ne modifient pas `data.db`.**

La suite vérifie les créations de groupes et de membres, les validations des dépenses, les dates limites, les deux exemples du professeur, l'ordre des participants, le payeur non participant, les petites sommes, la suppression et le recalcul, la somme des soldes, l'intégrité des transactions et la migration des anciennes données. Elle couvre aussi les modifications, les filtres, le CSV et un parcours complet dans l'interface.

Dernière vérification locale : **84 tests réussis**, avec Python 3.14.6, Streamlit 1.66.1 et pytest 9.2.0. Le serveur a également été démarré et les trois pages contrôlées dans un navigateur.

## Organisation du code

```text
base.sql                         Tables et exemples du professeur, ordre des participants
pytest.ini                       Configuration des tests de la version Streamlit
code-streamlit/
  app.py                         Interface et navigation entre les trois pages
  base.py                        Ouverture SQLite, initialisation et migration
  gestion.py                     Validations, opérations, répartition, soldes, filtres et CSV
  requirements.txt               Streamlit et pytest
  conftest.py                     Bases temporaires et données des tests
  test_base.py                   Initialisation, migration et intégrité SQLite
  test_gestion.py                Fonctionnalités obligatoires et calculs
  test_complements.py            Modification, filtres et CSV
  test_app.py                    Navigation et parcours utilisateur avec AppTest
```

## Périmètre et Git

Toutes les fonctionnalités obligatoires et les quatre compléments proposés sont implémentés. L'application est prévue pour un usage local, en euros, avec une répartition égale des dépenses. Elle ne comporte pas de comptes utilisateurs ni de synchronisation entre machines.

Le fichier `data.db`, l'environnement `.venv` et les caches Python sont ignorés par Git. Examiner `git status` et `git diff` avant de créer un commit. La publication sur GitHub reste une action manuelle après vérification du projet.
