"""Interface Streamlit du projet Partage de frais."""

import sqlite3
from contextlib import closing
from datetime import date, timedelta

import streamlit as st

from base import ouvrir_base
from gestion import (
    ajouter_depense,
    ajouter_membre,
    calculer_soldes,
    convertir_en_centimes,
    creer_groupe,
    exporter_csv,
    filtrer_depenses,
    formater_montant,
    lister_depenses,
    lister_groupes,
    lister_membres,
    modifier_depense,
    obtenir_groupe,
    supprimer_depense,
)


def date_fr(jour):
    return date.fromisoformat(jour).strftime("%d/%m/%Y")


def confirmer_action(message):
    st.session_state["message_succes"] = message
    st.rerun()


def afficher_groupes(conn, groupes, groupe):
    st.header("Groupes")
    st.write("Préparez votre séjour et réunissez ses membres.")
    with st.expander("Créer un groupe", expanded=True):
        with st.form("creation_groupe", clear_on_submit=True):
            nom = st.text_input("Nom du groupe", key="nom_groupe", placeholder="Week-end entre amis")
            debut_col, fin_col = st.columns(2)
            debut = debut_col.date_input("Début du séjour", value=date.today(), key="debut_groupe", format="DD/MM/YYYY")
            fin = fin_col.date_input("Fin du séjour", value=date.today() + timedelta(days=7), key="fin_groupe", format="DD/MM/YYYY")
            noms = st.text_area("Membres, un nom par ligne", key="noms_membres", placeholder="Alice\nBob\nChloé")
            st.caption("Vous pourrez ajouter d'autres membres après la création du groupe.")
            if st.form_submit_button("Créer le groupe", type="primary"):
                try:
                    groupe_id = creer_groupe(conn, nom, debut, fin, [n.strip() for n in noms.splitlines() if n.strip()])
                except ValueError as erreur:
                    st.error(str(erreur))
                else:
                    st.session_state["groupe_a_selectionner"] = groupe_id
                    confirmer_action("Le groupe a été créé.")

    st.subheader("Groupes existants")
    if groupes:
        st.dataframe([
            {"Groupe": g["nom"], "Début": date_fr(g["date_debut"]), "Fin": date_fr(g["date_fin"]), "Membres": g["nombre_membres"]}
            for g in groupes
        ], hide_index=True, use_container_width=True)
        st.caption("Choisissez le groupe actif dans la barre latérale pour consulter ses dépenses et ses soldes.")
    else:
        st.info("Créez votre premier groupe pour commencer.")

    if groupe is not None:
        st.subheader(f"Membres · {groupe['nom']}")
        membres = lister_membres(conn, groupe["id"])
        if membres:
            st.write(" · ".join(m["nom"] for m in membres))
        else:
            st.info("Ce groupe n'a pas encore de membre.")
        with st.form(f"ajout_membre_{groupe['id']}", clear_on_submit=True):
            nom_membre = st.text_input("Nom du nouveau membre", key=f"nouveau_membre_{groupe['id']}")
            if st.form_submit_button("Ajouter le membre"):
                try:
                    ajouter_membre(conn, groupe["id"], nom_membre)
                except ValueError as erreur:
                    st.error(str(erreur))
                else:
                    confirmer_action("Le membre a été ajouté.")


def afficher_formulaire_depense(conn, groupe, membres, depense=None):
    groupe_id = groupe["id"]
    ids = [m["id"] for m in membres]
    noms = {m["id"]: m["nom"] for m in membres}
    edition = depense is not None
    suffixe = f"edition_{depense['id']}" if edition else str(groupe_id)
    montant_initial = depense["montant_centimes"] if edition else 0
    with st.form(f"form_depense_{suffixe}", clear_on_submit=not edition):
        st.subheader("Modifier cette dépense" if edition else "Ajouter une dépense")
        libelle = st.text_input(
            "Libellé", value=depense["libelle"] if edition else "",
            key=f"libelle_{suffixe}", placeholder="Courses, essence, restaurant…",
        )
        montant_col, date_col = st.columns(2)
        montant = montant_col.text_input(
            "Montant (€)", value=f"{montant_initial // 100},{montant_initial % 100:02d}" if edition else "",
            key=f"montant_{suffixe}", placeholder="30,00",
        )
        jour = date_col.date_input(
            "Date de la dépense", value=date.fromisoformat(depense["date"] if edition else groupe["date_debut"]),
            min_value=date.fromisoformat(groupe["date_debut"]),
            max_value=date.fromisoformat(groupe["date_fin"]), key=f"date_depense_{suffixe}", format="DD/MM/YYYY",
        )
        payeur = st.selectbox(
            "Payé par", ids, index=ids.index(depense["payeur_id"]) if edition else 0,
            format_func=noms.get, key=f"payeur_{suffixe}",
        )
        participants = st.multiselect(
            "Participants", ids, default=[p["membre_id"] for p in depense["participants"]] if edition else [],
            format_func=noms.get, key=f"participants_{suffixe}",
            placeholder="Sélectionnez les membres dans l'ordre souhaité",
        )
        st.caption("La dépense est partagée à parts égales. Les centimes restants sont dus par le premier participant sélectionné.")
        if st.form_submit_button("Enregistrer les modifications" if edition else "Enregistrer la dépense", type="primary"):
            try:
                centimes = convertir_en_centimes(montant)
                if edition:
                    modifier_depense(conn, groupe_id, depense["id"], libelle, centimes, jour, payeur, participants)
                else:
                    ajouter_depense(conn, groupe_id, libelle, centimes, jour, payeur, participants)
            except ValueError as erreur:
                st.error(str(erreur))
            else:
                confirmer_action("La dépense a été modifiée. Les soldes sont à jour." if edition else "La dépense a été enregistrée. Les soldes sont à jour.")


def afficher_depenses(conn, groupe):
    st.header("Dépenses")
    membres = lister_membres(conn, groupe["id"])
    if not membres:
        st.info("Ajoutez d'abord un membre sur la page Groupes.")
        return
    afficher_formulaire_depense(conn, groupe, membres)
    depenses = lister_depenses(conn, groupe["id"])
    st.subheader("Dépenses du groupe")
    if not depenses:
        st.info("Aucune dépense pour ce séjour. Ajoutez la première ci-dessus.")
        return
    nombre_col, total_col = st.columns(2)
    nombre_col.metric("Dépenses enregistrées", len(depenses))
    total_col.metric("Total du séjour", formater_montant(sum(d["montant_centimes"] for d in depenses)))
    membre_col, debut_col, fin_col = st.columns(3)
    noms = {m["id"]: m["nom"] for m in membres}
    membre_filtre = membre_col.selectbox(
        "Membre concerné", [None, *noms], format_func=lambda identifiant: noms.get(identifiant, "Tous les membres"),
        key=f"filtre_membre_{groupe['id']}",
    )
    debut = debut_col.date_input(
        "À partir du", value=date.fromisoformat(groupe["date_debut"]),
        min_value=date.fromisoformat(groupe["date_debut"]), max_value=date.fromisoformat(groupe["date_fin"]),
        key=f"filtre_debut_{groupe['id']}", format="DD/MM/YYYY",
    )
    fin = fin_col.date_input(
        "Jusqu'au", value=date.fromisoformat(groupe["date_fin"]),
        min_value=date.fromisoformat(groupe["date_debut"]), max_value=date.fromisoformat(groupe["date_fin"]),
        key=f"filtre_fin_{groupe['id']}", format="DD/MM/YYYY",
    )
    st.caption("Dépenses payées par le membre sélectionné ou auxquelles il participe. Les deux dates sont incluses.")
    try:
        depenses = filtrer_depenses(depenses, membre_filtre, debut, fin)
    except ValueError as erreur:
        st.error(str(erreur))
        return
    st.download_button(
        "Exporter les dépenses affichées (CSV)", exporter_csv(depenses),
        file_name=f"depenses_groupe_{groupe['id']}.csv", mime="text/csv", disabled=not depenses,
    )
    if not depenses:
        st.info("Aucune dépense ne correspond aux filtres.")
        return
    st.dataframe([
        {"Date": date_fr(d["date"]), "Libellé": d["libelle"], "Montant": formater_montant(d["montant_centimes"]),
         "Payeur": d["payeur"], "Participants": len(d["participants"])}
        for d in depenses
    ], hide_index=True, use_container_width=True)
    for depense in depenses:
        with st.expander(f"{date_fr(depense['date'])} · {depense['libelle']} · {formater_montant(depense['montant_centimes'])}"):
            st.write(f"Payé par **{depense['payeur']}**")
            st.caption("Participants dans leur ordre d'ajout et part due par chacun.")
            st.dataframe([
                {"Ordre": i + 1, "Participant": p["nom"], "Part due": formater_montant(p["part_centimes"])}
                for i, p in enumerate(depense["participants"])
            ], hide_index=True, use_container_width=True)
            afficher_formulaire_depense(conn, groupe, membres, depense)
            if st.button("Supprimer la dépense", key=f"supprimer_{depense['id']}"):
                try:
                    supprimer_depense(conn, groupe["id"], depense["id"])
                except ValueError as erreur:
                    st.error(str(erreur))
                else:
                    confirmer_action("La dépense a été supprimée. Les soldes sont à jour.")


def afficher_soldes(conn, groupe):
    st.header("Soldes")
    soldes = calculer_soldes(conn, groupe["id"])
    if not soldes:
        st.info("Ajoutez d'abord un membre sur la page Groupes.")
        return
    st.caption("Solde = montant payé − parts dues. Un solde positif est une somme à recevoir ; un solde négatif est à rembourser.")
    st.metric("Total des dépenses du séjour", formater_montant(sum(s["paye_centimes"] for s in soldes)))
    st.dataframe([
        {"Membre": s["nom"], "Montant payé": formater_montant(s["paye_centimes"]),
         "Parts dues": formater_montant(s["du_centimes"]), "Solde": formater_montant(s["solde_centimes"], signe=True),
         "Situation": "À recevoir" if s["solde_centimes"] > 0 else "À rembourser" if s["solde_centimes"] < 0 else "Équilibré"}
        for s in soldes
    ], hide_index=True, use_container_width=True)
    somme = sum(s["solde_centimes"] for s in soldes)
    if somme == 0:
        st.success("La somme des soldes est de 0,00 €.")
    else:
        st.error("Les soldes ne sont pas équilibrés. Vérifiez les données du groupe.")


def main():
    st.set_page_config(page_title="Partage de frais", page_icon="💶", layout="wide")
    st.title("Partage de frais")
    st.caption("Les dépenses du séjour, les comptes en toute clarté.")
    try:
        with closing(ouvrir_base()) as conn:
            groupes = lister_groupes(conn)
            st.sidebar.title("Votre séjour")
            page = st.sidebar.radio("Navigation", ["Groupes", "Dépenses", "Soldes"], key="navigation")
            groupe = None
            if groupes:
                ids = [g["id"] for g in groupes]
                noms = {g["id"]: f"{g['nom']} · #{g['id']}" for g in groupes}
                nouveau_id = st.session_state.pop("groupe_a_selectionner", None)
                if nouveau_id in ids:
                    st.session_state["groupe_actif"] = nouveau_id
                elif st.session_state.get("groupe_actif") not in ids:
                    st.session_state["groupe_actif"] = ids[0]
                groupe_id = st.sidebar.selectbox("Groupe actif", ids, format_func=noms.get, key="groupe_actif")
                groupe = obtenir_groupe(conn, groupe_id)
                st.sidebar.caption(f"Du {date_fr(groupe['date_debut'])} au {date_fr(groupe['date_fin'])}")
            message = st.session_state.pop("message_succes", None)
            if message:
                st.success(message)
            if groupe is not None:
                st.write(f"**Séjour sélectionné : {groupe['nom']}**")
            if page == "Groupes":
                afficher_groupes(conn, groupes, groupe)
            elif groupe is None:
                st.info("Créez un groupe sur la page Groupes pour commencer.")
            elif page == "Dépenses":
                afficher_depenses(conn, groupe)
            else:
                afficher_soldes(conn, groupe)
    except sqlite3.Error:
        st.error("Impossible d'accéder aux données. Vérifiez que le fichier de la base est accessible, puis réessayez.")


if __name__ == "__main__":
    main()
