import csv
import sqlite3
from io import StringIO

import pytest

from gestion import (
    ajouter_depense,
    calculer_soldes,
    exporter_csv,
    filtrer_depenses,
    lister_depenses,
    modifier_depense,
)


def test_modification_depense_et_recalcul(conn, groupe):
    groupe_id, ids = groupe
    depense_id = ajouter_depense(conn, groupe_id, "Courses", 3000, "2026-07-02", ids[0], ids)
    modifier_depense(conn, groupe_id, depense_id, "Restaurant", 1000, "2026-07-08", ids[1], [ids[2], ids[0], ids[1]])
    depense = lister_depenses(conn, groupe_id)[0]
    assert depense["libelle"] == "Restaurant"
    assert depense["date"] == "2026-07-08"
    assert depense["payeur_id"] == ids[1]
    assert [p["membre_id"] for p in depense["participants"]] == [ids[2], ids[0], ids[1]]
    assert [s["solde_centimes"] for s in calculer_soldes(conn, groupe_id)] == [-333, 667, -334]
    assert sum(s["solde_centimes"] for s in calculer_soldes(conn, groupe_id)) == 0


@pytest.mark.parametrize("montant,jour,payeur,participants", [
    (0, "2026-07-02", 0, [0, 1, 2]),
    (1000, "2026-07-09", 0, [0, 1, 2]),
    (1000, "2026-07-02", 1, []),
])
def test_modification_invalide_preserve_depense_et_soldes(conn, groupe, montant, jour, payeur, participants):
    groupe_id, ids = groupe
    depense_id = ajouter_depense(conn, groupe_id, "Courses", 3000, "2026-07-02", ids[0], ids)
    avant = lister_depenses(conn, groupe_id)
    with pytest.raises(ValueError):
        modifier_depense(conn, groupe_id, depense_id, "Invalide", montant, jour, ids[payeur], [ids[i] for i in participants])
    assert lister_depenses(conn, groupe_id) == avant
    assert [s["solde_centimes"] for s in calculer_soldes(conn, groupe_id)] == [2000, -1000, -1000]


def test_modification_autre_groupe_refusee(conn, groupe):
    groupe_id, ids = groupe
    with pytest.raises(ValueError, match="groupe"):
        modifier_depense(conn, groupe_id, 1, "Invalide", 1000, "2026-07-02", ids[0], ids)
    assert lister_depenses(conn, 1)[0]["libelle"] == "Courses"


def test_modification_transactionnelle_restaure_anciens_participants(conn, groupe):
    groupe_id, ids = groupe
    depense_id = ajouter_depense(conn, groupe_id, "Courses", 3000, "2026-07-02", ids[0], ids)
    avant = lister_depenses(conn, groupe_id)
    conn.execute(f"CREATE TRIGGER refuser_participant BEFORE INSERT ON participants WHEN NEW.membre_id = {ids[1]} BEGIN SELECT RAISE(ABORT, 'échec simulé'); END")
    with pytest.raises(sqlite3.IntegrityError):
        modifier_depense(conn, groupe_id, depense_id, "À annuler", 999, "2026-07-03", ids[2], ids)
    assert lister_depenses(conn, groupe_id) == avant


def test_filtres_par_payeur_participant_et_periode(conn, groupe):
    groupe_id, ids = groupe
    premiere = ajouter_depense(conn, groupe_id, "Cadeau", 1000, "2026-07-01", ids[0], [ids[1]])
    seconde = ajouter_depense(conn, groupe_id, "Repas", 500, "2026-07-08", ids[2], [ids[2]])
    depenses = lister_depenses(conn, groupe_id)
    assert [d["id"] for d in filtrer_depenses(depenses, membre_id=ids[0])] == [premiere]
    assert [d["id"] for d in filtrer_depenses(depenses, membre_id=ids[1])] == [premiere]
    assert [d["id"] for d in filtrer_depenses(depenses, date_debut="2026-07-08", date_fin="2026-07-08")] == [seconde]
    assert filtrer_depenses(depenses, ids[0], "2026-07-08", "2026-07-08") == []
    assert [s["solde_centimes"] for s in calculer_soldes(conn, groupe_id)] == [1000, -1000, 0]


@pytest.mark.parametrize("debut,fin", [("2026-07-08", "2026-07-01"), ("invalide", "2026-07-08")])
def test_filtre_dates_invalides(debut, fin):
    with pytest.raises(ValueError):
        filtrer_depenses([], date_debut=debut, date_fin=fin)


def test_csv_montant_exact_accents_et_ordre(conn, groupe):
    groupe_id, ids = groupe
    ajouter_depense(conn, groupe_id, 'Dîner; "été"', 1001, "2026-07-02", ids[0], [ids[2], ids[1]])
    contenu = exporter_csv(lister_depenses(conn, groupe_id))
    assert contenu.startswith(b"\xef\xbb\xbf")
    lignes = list(csv.DictReader(StringIO(contenu.decode("utf-8-sig")), delimiter=";"))
    assert lignes == [{
        "Date": "2026-07-02", "Libellé": 'Dîner; "été"', "Montant (€)": "10,01",
        "Payeur": "Alice", "Participants (ordre)": "Chloé → Bob",
    }]


def test_csv_ne_produit_pas_de_formule_excel(conn, groupe):
    groupe_id, ids = groupe
    ajouter_depense(conn, groupe_id, "=1+1", 1000, "2026-07-02", ids[0], ids)
    lignes = list(csv.DictReader(StringIO(exporter_csv(lister_depenses(conn, groupe_id)).decode("utf-8-sig")), delimiter=";"))
    assert lignes[0]["Libellé"] == "'=1+1"
