import sqlite3
from contextlib import closing

import pytest

from base import ouvrir_base
from gestion import calculer_soldes, lister_depenses, lister_groupes


def test_exemples_conserves_et_cles_etrangeres(conn):
    assert lister_groupes(conn)[0]["nom"] == "Vacances à Spa"
    assert [s["solde_centimes"] for s in calculer_soldes(conn, 1)] == [2000, -1000, -1000]
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError), conn:
        conn.execute("INSERT INTO membres (groupe_id, nom) VALUES (999, 'Invalide')")


def test_reouverture_ne_duplique_pas_les_exemples(conn, base_isolee):
    with closing(ouvrir_base(base_isolee)) as autre:
        assert len(lister_groupes(autre)) == 1
        assert len(lister_depenses(autre, 1)) == 1


def test_initialisation_fichier_vide(base_isolee):
    base_isolee.touch()
    with closing(ouvrir_base(base_isolee)) as conn:
        assert len(lister_groupes(conn)) == 1


def test_migration_ancien_schema_preserve_donnees_et_ordre(base_isolee):
    with closing(sqlite3.connect(base_isolee)) as ancienne:
        ancienne.executescript("""
            CREATE TABLE groupes (id INTEGER PRIMARY KEY, nom TEXT NOT NULL, date_debut TEXT NOT NULL, date_fin TEXT NOT NULL);
            CREATE TABLE membres (id INTEGER PRIMARY KEY, groupe_id INTEGER NOT NULL REFERENCES groupes(id) ON DELETE CASCADE, nom TEXT NOT NULL);
            CREATE TABLE depenses (id INTEGER PRIMARY KEY, groupe_id INTEGER NOT NULL REFERENCES groupes(id) ON DELETE CASCADE,
                libelle TEXT NOT NULL, montant_centimes INTEGER NOT NULL, date TEXT NOT NULL, payeur_id INTEGER NOT NULL REFERENCES membres(id));
            CREATE TABLE participants (depense_id INTEGER NOT NULL REFERENCES depenses(id) ON DELETE CASCADE,
                membre_id INTEGER NOT NULL REFERENCES membres(id), PRIMARY KEY (depense_id, membre_id));
            INSERT INTO groupes VALUES (1, 'Ancien séjour', '2026-07-01', '2026-07-08');
            INSERT INTO membres VALUES (1, 1, 'Alice'), (2, 1, 'Bob'), (3, 1, 'Chloé');
            INSERT INTO depenses VALUES (1, 1, 'Ancienne dépense', 1000, '2026-07-02', 1);
            INSERT INTO participants VALUES (1, 3), (1, 1), (1, 2);
        """)
    for _ in range(2):
        with closing(ouvrir_base(base_isolee)) as conn:
            assert lister_groupes(conn)[0]["nom"] == "Ancien séjour"
            participants = lister_depenses(conn, 1)[0]["participants"]
            assert [p["membre_id"] for p in participants] == [3, 1, 2]
            assert [p["ordre"] for p in participants] == [0, 1, 2]
            assert [s["solde_centimes"] for s in calculer_soldes(conn, 1)] == [667, -333, -334]
            with pytest.raises(sqlite3.IntegrityError), conn:
                conn.execute("UPDATE participants SET ordre = 0 WHERE membre_id = 1")
