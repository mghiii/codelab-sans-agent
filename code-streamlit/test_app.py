from pathlib import Path
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from gestion import calculer_soldes, creer_groupe, lister_depenses, lister_groupes, lister_membres


def cliquer(page, libelle):
    next(bouton for bouton in page.button if bouton.label == libelle).click().run()
    assert not page.exception


def test_accueil():
    page = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=60).run()
    assert not page.exception


@pytest.mark.parametrize("vue", ["Groupes", "Dépenses", "Soldes"])
def test_navigation(vue):
    page = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=60).run()
    page.radio(key="navigation").set_value(vue).run()
    assert not page.exception
    assert page.header[0].value == vue


def test_parcours_creation_membre_depense_modification_suppression(conn):
    page = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=60).run()
    page.text_input(key="nom_groupe").set_value("Week-end")
    page.date_input(key="debut_groupe").set_value(date(2026, 7, 1))
    page.date_input(key="fin_groupe").set_value(date(2026, 7, 8))
    page.text_area(key="noms_membres").set_value("Alice\nBob\nChloé")
    cliquer(page, "Créer le groupe")
    groupe_id = lister_groupes(conn)[-1]["id"]
    assert page.selectbox(key="groupe_actif").value == groupe_id
    page.text_input(key=f"nouveau_membre_{groupe_id}").set_value("David")
    cliquer(page, "Ajouter le membre")
    ids = [m["id"] for m in lister_membres(conn, groupe_id)]
    assert len(ids) == 4

    page.radio(key="navigation").set_value("Dépenses").run()
    page.text_input(key=f"libelle_{groupe_id}").set_value("Courses")
    page.text_input(key=f"montant_{groupe_id}").set_value("10,00")
    page.multiselect(key=f"participants_{groupe_id}").set_value([ids[2], ids[0], ids[1]])
    cliquer(page, "Enregistrer la dépense")
    depense = lister_depenses(conn, groupe_id)[0]
    assert [p["membre_id"] for p in depense["participants"]] == [ids[2], ids[0], ids[1]]
    page.radio(key="navigation").set_value("Soldes").run()
    assert not page.exception
    assert page.dataframe[0].value["Solde"].tolist() == ["+6,67 €", "−3,33 €", "−3,34 €", "0,00 €"]

    page.radio(key="navigation").set_value("Dépenses").run()
    page.text_input(key=f"montant_edition_{depense['id']}").set_value("30,00")
    cliquer(page, "Enregistrer les modifications")
    assert [s["solde_centimes"] for s in calculer_soldes(conn, groupe_id)] == [2000, -1000, -1000, 0]
    page.button(key=f"supprimer_{depense['id']}").click().run()
    assert not page.exception
    assert lister_depenses(conn, groupe_id) == []
    page.radio(key="navigation").set_value("Soldes").run()
    assert page.dataframe[0].value["Solde"].tolist() == ["0,00 €"] * 4


def test_interface_refuse_depense_nulle(conn):
    page = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=60).run()
    page.radio(key="navigation").set_value("Dépenses").run()
    page.text_input(key="libelle_1").set_value("Invalide")
    page.text_input(key="montant_1").set_value("0")
    page.multiselect(key="participants_1").set_value([1, 2, 3])
    cliquer(page, "Enregistrer la dépense")
    assert "strictement positif" in page.error[0].value
    assert len(lister_depenses(conn, 1)) == 1


def test_interface_refuse_dates_groupe_inversees(conn):
    page = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=60).run()
    page.text_input(key="nom_groupe").set_value("Invalide")
    page.date_input(key="debut_groupe").set_value(date(2026, 7, 8))
    page.date_input(key="fin_groupe").set_value(date(2026, 7, 1))
    cliquer(page, "Créer le groupe")
    assert "précéder" in page.error[0].value
    assert len(lister_groupes(conn)) == 1


def test_groupe_vide_et_changement_de_groupe(conn):
    groupe_id = creer_groupe(conn, "Vide", "2026-07-01", "2026-07-08")
    page = AppTest.from_file(str(Path(__file__).parent / "app.py"), default_timeout=60).run()
    page.selectbox(key="groupe_actif").set_value(groupe_id).run()
    page.radio(key="navigation").set_value("Dépenses").run()
    assert not page.exception
    assert "Ajoutez d'abord" in page.info[0].value
    page.selectbox(key="groupe_actif").set_value(1).run()
    assert not page.exception
    assert len(page.expander) == 1
