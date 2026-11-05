import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from gestion import (
    MAX_CENTIMES,
    ajouter_depense,
    ajouter_membre,
    calculer_soldes,
    convertir_en_centimes,
    creer_groupe,
    formater_montant,
    lister_depenses,
    lister_groupes,
    lister_membres,
    obtenir_groupe,
    repartir_centimes,
    supprimer_depense,
)


def soldes_par_nom(conn, groupe_id):
    return {s["nom"]: s["solde_centimes"] for s in calculer_soldes(conn, groupe_id)}


def test_creation_groupe_et_membres(conn):
    groupe_id = creer_groupe(conn, "  Ardennes  ", date(2026, 7, 1), date(2026, 7, 8), [" Alice ", "Bob"])
    groupe = obtenir_groupe(conn, groupe_id)
    assert groupe["nom"] == "Ardennes"
    assert groupe["date_debut"] == "2026-07-01"
    assert groupe["date_fin"] == "2026-07-08"
    assert [m["nom"] for m in lister_membres(conn, groupe_id)] == ["Alice", "Bob"]
    assert lister_groupes(conn)[-1]["nombre_membres"] == 2


def test_groupe_sans_membre_et_ajout_ulterieur(conn):
    groupe_id = creer_groupe(conn, "Journée", "2026-07-01", "2026-07-01")
    assert calculer_soldes(conn, groupe_id) == []
    membre_id = ajouter_membre(conn, groupe_id, " Alice ")
    assert lister_membres(conn, groupe_id)[0]["id"] == membre_id
    assert soldes_par_nom(conn, groupe_id) == {"Alice": 0}


@pytest.mark.parametrize("nom,debut,fin,noms", [
    (" ", "2026-07-01", "2026-07-08", []),
    ("Test", "2026-07-08", "2026-07-01", []),
    ("Test", "2026-02-30", "2026-07-08", []),
    ("Test", "2026-07-01", "invalide", []),
    ("Test", "2026-07-01", "2026-07-08", ["Alice", " alice "]),
    ("Test", "2026-07-01", "2026-07-08", [" "]),
])
def test_groupe_invalide_sans_ecriture(conn, nom, debut, fin, noms):
    avant = len(lister_groupes(conn))
    with pytest.raises(ValueError):
        creer_groupe(conn, nom, debut, fin, noms)
    assert len(lister_groupes(conn)) == avant


@pytest.mark.parametrize("nom", ["", "  ", "alice", " ALICE "])
def test_membre_invalide_ou_duplique(conn, groupe, nom):
    groupe_id, _ = groupe
    with pytest.raises(ValueError):
        ajouter_membre(conn, groupe_id, nom)
    assert len(lister_membres(conn, groupe_id)) == 3


def test_refus_membre_groupe_inexistant(conn):
    with pytest.raises(ValueError, match="groupe"):
        ajouter_membre(conn, 999, "Alice")


def test_creation_groupe_transactionnelle(conn):
    conn.execute("CREATE TRIGGER refuser_bob BEFORE INSERT ON membres WHEN NEW.nom = 'Bob' BEGIN SELECT RAISE(ABORT, 'échec simulé'); END")
    avant = len(lister_groupes(conn))
    with pytest.raises(sqlite3.IntegrityError):
        creer_groupe(conn, "À annuler", "2026-07-01", "2026-07-08", ["Alice", "Bob"])
    assert len(lister_groupes(conn)) == avant
    assert conn.execute("SELECT COUNT(*) FROM membres").fetchone()[0] == 3


def test_ajout_depense_valide_et_details(conn, groupe):
    groupe_id, ids = groupe
    depense_id = ajouter_depense(conn, groupe_id, " Courses ", 3000, date(2026, 7, 2), ids[0], ids)
    depense = lister_depenses(conn, groupe_id)[0]
    assert depense["id"] == depense_id
    assert depense["libelle"] == "Courses"
    assert depense["montant_centimes"] == 3000
    assert depense["date"] == "2026-07-02"
    assert depense["payeur"] == "Alice"
    assert [p["membre_id"] for p in depense["participants"]] == ids
    assert [p["ordre"] for p in depense["participants"]] == [0, 1, 2]
    assert [p["part_centimes"] for p in depense["participants"]] == [1000, 1000, 1000]


@pytest.mark.parametrize("montant", [0, -100, 12.5, True, MAX_CENTIMES + 1])
def test_refus_montant_invalide(conn, groupe, montant):
    groupe_id, ids = groupe
    with pytest.raises(ValueError, match="montant"):
        ajouter_depense(conn, groupe_id, "Courses", montant, "2026-07-02", ids[0], ids)
    assert lister_depenses(conn, groupe_id) == []
    assert set(soldes_par_nom(conn, groupe_id).values()) == {0}


@pytest.mark.parametrize("jour", ["2026-06-30", "2026-07-09", "2026-02-30", "invalide"])
def test_refus_depense_hors_sejour_ou_date_invalide(conn, groupe, jour):
    groupe_id, ids = groupe
    with pytest.raises(ValueError):
        ajouter_depense(conn, groupe_id, "Courses", 1000, jour, ids[0], ids)
    assert lister_depenses(conn, groupe_id) == []


@pytest.mark.parametrize("jour", ["2026-07-01", "2026-07-08"])
def test_dates_limites_du_sejour_acceptees(conn, groupe, jour):
    groupe_id, ids = groupe
    ajouter_depense(conn, groupe_id, "Courses", 1000, jour, ids[0], ids)
    assert len(lister_depenses(conn, groupe_id)) == 1


def test_refus_payeur_exterieur(conn, groupe):
    groupe_id, ids = groupe
    with pytest.raises(ValueError, match="payeur"):
        ajouter_depense(conn, groupe_id, "Courses", 1000, "2026-07-02", 1, ids)
    assert lister_depenses(conn, groupe_id) == []


def test_refus_participant_exterieur(conn, groupe):
    groupe_id, ids = groupe
    with pytest.raises(ValueError, match="participants"):
        ajouter_depense(conn, groupe_id, "Courses", 1000, "2026-07-02", ids[0], [ids[0], 1])
    assert lister_depenses(conn, groupe_id) == []


@pytest.mark.parametrize("participants", [[], [999], [1, 1], [True]])
def test_refus_participants_invalides(conn, groupe, participants):
    groupe_id, ids = groupe
    with pytest.raises(ValueError):
        ajouter_depense(conn, groupe_id, "Courses", 1000, "2026-07-02", ids[0], participants)
    assert lister_depenses(conn, groupe_id) == []


def test_refus_participant_duplique_du_groupe(conn, groupe):
    groupe_id, ids = groupe
    with pytest.raises(ValueError, match="seule fois"):
        ajouter_depense(conn, groupe_id, "Courses", 1000, "2026-07-02", ids[0], [ids[0], ids[0]])
    assert lister_depenses(conn, groupe_id) == []


def test_refus_libelle_vide(conn, groupe):
    groupe_id, ids = groupe
    with pytest.raises(ValueError, match="libellé"):
        ajouter_depense(conn, groupe_id, " ", 1000, "2026-07-02", ids[0], ids)


@pytest.mark.parametrize("montant,attendus", [
    (3000, {"Alice": 2000, "Bob": -1000, "Chloé": -1000}),
    (1000, {"Alice": 666, "Bob": -333, "Chloé": -333}),
])
def test_exemples_du_professeur(conn, groupe, montant, attendus):
    groupe_id, ids = groupe
    ajouter_depense(conn, groupe_id, "Courses", montant, "2026-07-02", ids[0], ids)
    assert soldes_par_nom(conn, groupe_id) == attendus
    soldes = calculer_soldes(conn, groupe_id)
    assert sum(s["paye_centimes"] for s in soldes) == montant
    assert sum(s["du_centimes"] for s in soldes) == montant
    assert sum(s["solde_centimes"] for s in soldes) == 0


def test_reste_attribue_au_premier_participant_selectionne(conn, groupe):
    groupe_id, ids = groupe
    ajouter_depense(conn, groupe_id, "Courses", 1000, "2026-07-02", ids[0], [ids[2], ids[0], ids[1]])
    assert soldes_par_nom(conn, groupe_id) == {"Alice": 667, "Bob": -333, "Chloé": -334}
    assert [p["nom"] for p in lister_depenses(conn, groupe_id)[0]["participants"]] == ["Chloé", "Alice", "Bob"]


def test_payeur_non_participant(conn, groupe):
    groupe_id, ids = groupe
    ajouter_depense(conn, groupe_id, "Cadeau", 1000, "2026-07-02", ids[0], ids[1:])
    assert soldes_par_nom(conn, groupe_id) == {"Alice": 1000, "Bob": -500, "Chloé": -500}


def test_reste_superieur_a_un_centime_et_tres_petits_montants():
    assert repartir_centimes(5, [3, 2, 1]) == {3: 3, 2: 1, 1: 1}
    assert repartir_centimes(2, [3, 2, 1]) == {3: 2, 2: 0, 1: 0}


def test_soldes_zero_apres_plusieurs_depenses(conn, groupe):
    groupe_id, ids = groupe
    ajouter_depense(conn, groupe_id, "Courses", 1000, "2026-07-02", ids[0], ids)
    ajouter_depense(conn, groupe_id, "Essence", 2345, "2026-07-03", ids[1], [ids[2], ids[0]])
    ajouter_depense(conn, groupe_id, "Activité", 1, "2026-07-04", ids[2], [ids[1]])
    assert soldes_par_nom(conn, groupe_id) == {"Alice": -506, "Bob": 2011, "Chloé": -1505}
    assert sum(s["solde_centimes"] for s in calculer_soldes(conn, groupe_id)) == 0


def test_suppression_et_recalcul_avec_cascade(conn, groupe):
    groupe_id, ids = groupe
    depense_id = ajouter_depense(conn, groupe_id, "Courses", 1000, "2026-07-02", ids[0], ids)
    supprimer_depense(conn, groupe_id, depense_id)
    assert lister_depenses(conn, groupe_id) == []
    assert conn.execute("SELECT COUNT(*) FROM participants WHERE depense_id = ?", (depense_id,)).fetchone()[0] == 0
    assert soldes_par_nom(conn, groupe_id) == {"Alice": 0, "Bob": 0, "Chloé": 0}
    assert sum(s["solde_centimes"] for s in calculer_soldes(conn, groupe_id)) == 0


def test_suppression_preserve_les_autres_depenses_et_groupes(conn, groupe):
    groupe_id, ids = groupe
    premiere = ajouter_depense(conn, groupe_id, "Courses", 1000, "2026-07-02", ids[0], ids)
    ajouter_depense(conn, groupe_id, "Essence", 600, "2026-07-03", ids[1], ids)
    with pytest.raises(ValueError, match="groupe"):
        supprimer_depense(conn, groupe_id, 1)
    supprimer_depense(conn, groupe_id, premiere)
    assert soldes_par_nom(conn, groupe_id) == {"Alice": -200, "Bob": 400, "Chloé": -200}
    assert len(lister_depenses(conn, 1)) == 1


def test_depense_transactionnelle_si_insertion_participant_echoue(conn, groupe):
    groupe_id, ids = groupe
    conn.execute(f"CREATE TRIGGER refuser_participant BEFORE INSERT ON participants WHEN NEW.membre_id = {ids[1]} BEGIN SELECT RAISE(ABORT, 'échec simulé'); END")
    avant = conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        ajouter_depense(conn, groupe_id, "À annuler", 1000, "2026-07-02", ids[0], ids)
    assert lister_depenses(conn, groupe_id) == []
    assert conn.execute("SELECT COUNT(*) FROM participants").fetchone()[0] == avant


@pytest.mark.parametrize("euros,centimes", [("10,01", 1001), ("0.01", 1), (" 30,00 ", 3000), (Decimal("2.50"), 250)])
def test_conversion_exacte_en_centimes(euros, centimes):
    assert convertir_en_centimes(euros) == centimes


@pytest.mark.parametrize("euros", ["0", "-1", "NaN", "Infinity", "abc", "", "0,001", "10.999", "1e1000", "1.000000000000000000000000000001"])
def test_conversion_refuse_montant_invalide(euros):
    with pytest.raises(ValueError):
        convertir_en_centimes(euros)


@pytest.mark.parametrize("centimes,signe,attendu", [
    (0, True, "0,00 €"), (1000, True, "+10,00 €"), (-333, True, "−3,33 €"),
    (123456789, False, "1 234 567,89 €"),
])
def test_affichage_des_montants(centimes, signe, attendu):
    assert formater_montant(centimes, signe) == attendu
