"""Règles du partage de frais, indépendantes de l'interface Streamlit.

Toutes les valeurs monétaires, y compris les résultats, sont des centimes entiers.
Les écritures d'un groupe ou d'une dépense sont réalisées dans une transaction.
"""

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import StringIO


MAX_CENTIMES = 2**63 - 1  # Limite des entiers stockés par SQLite.


def _texte_non_vide(valeur, champ):
    if not isinstance(valeur, str) or not valeur.strip():
        raise ValueError(f"{champ} ne peut pas être vide.")
    return valeur.strip()


def _date_iso(valeur):
    if isinstance(valeur, date) and not isinstance(valeur, datetime):
        return valeur.isoformat()
    if isinstance(valeur, str):
        try:
            return date.fromisoformat(valeur).isoformat()
        except ValueError:
            pass
    raise ValueError("Saisissez une date valide (AAAA-MM-JJ).")


def _valider_centimes(montant_centimes):
    if type(montant_centimes) is not int or not 0 < montant_centimes <= MAX_CENTIMES:
        raise ValueError("Le montant doit être strictement positif, en centimes entiers, et compatible avec SQLite.")


def convertir_en_centimes(montant):
    """Convertit des euros sans arrondi silencieux, par exemple '10,01' → 1001."""
    try:
        euros = Decimal(str(montant).strip().replace(",", "."))
    except InvalidOperation:
        raise ValueError("Saisissez un montant en euros, par exemple 10,50.") from None
    if not euros.is_finite() or euros <= 0 or euros > Decimal(MAX_CENTIMES) / 100:
        raise ValueError("Le montant doit être strictement positif et compatible avec SQLite.")
    if euros != euros.quantize(Decimal("0.01")):
        raise ValueError("Le montant ne peut pas comporter de fraction de centime.")
    return int(euros * 100)


def formater_montant(centimes, signe=False):
    """Affiche des centimes en euros sans passer par un nombre flottant."""
    euros, reste = divmod(abs(centimes), 100)
    prefixe = "−" if centimes < 0 else "+" if signe and centimes > 0 else ""
    euros_formates = f"{euros:,}".replace(",", " ")
    return f"{prefixe}{euros_formates},{reste:02d} €"


def lister_groupes(conn):
    return conn.execute(
        "SELECT g.*, (SELECT COUNT(*) FROM membres m WHERE m.groupe_id = g.id) AS nombre_membres "
        "FROM groupes g ORDER BY g.id"
    ).fetchall()


def obtenir_groupe(conn, groupe_id):
    groupe = conn.execute("SELECT * FROM groupes WHERE id = ?", (groupe_id,)).fetchone()
    if groupe is None:
        raise ValueError("Ce groupe n'existe pas.")
    return groupe


def lister_membres(conn, groupe_id):
    obtenir_groupe(conn, groupe_id)
    return conn.execute(
        "SELECT * FROM membres WHERE groupe_id = ? ORDER BY id", (groupe_id,)
    ).fetchall()


def creer_groupe(conn, nom, date_debut, date_fin, noms_membres=()):
    nom = _texte_non_vide(nom, "Le nom du groupe")
    debut, fin = _date_iso(date_debut), _date_iso(date_fin)
    if fin < debut:
        raise ValueError("La fin du séjour ne peut pas précéder son début.")
    if isinstance(noms_membres, str):
        raise ValueError("Fournissez une liste de noms de membres.")
    noms = [_texte_non_vide(nom, "Le nom d'un membre") for nom in noms_membres]
    if len({nom.casefold() for nom in noms}) != len(noms):
        raise ValueError("Chaque membre doit avoir un nom différent dans le groupe.")
    with conn:
        curseur = conn.execute(
            "INSERT INTO groupes (nom, date_debut, date_fin) VALUES (?, ?, ?)",
            (nom, debut, fin),
        )
        groupe_id = curseur.lastrowid
        conn.executemany(
            "INSERT INTO membres (groupe_id, nom) VALUES (?, ?)",
            [(groupe_id, nom) for nom in noms],
        )
    return groupe_id


def ajouter_membre(conn, groupe_id, nom):
    nom = _texte_non_vide(nom, "Le nom du membre")
    with conn:
        membres = lister_membres(conn, groupe_id)
        if any(membre["nom"].casefold() == nom.casefold() for membre in membres):
            raise ValueError("Un membre porte déjà ce nom dans le groupe.")
        curseur = conn.execute("INSERT INTO membres (groupe_id, nom) VALUES (?, ?)", (groupe_id, nom))
    return curseur.lastrowid


def repartir_centimes(montant_centimes, participants):
    """Attribue tout le reste de la division au premier participant de la liste."""
    _valider_centimes(montant_centimes)
    participants = list(participants)
    if not participants:
        raise ValueError("Choisissez au moins un participant.")
    if any(type(membre_id) is not int for membre_id in participants):
        raise ValueError("Les participants doivent être des identifiants de membres.")
    if len(set(participants)) != len(participants):
        raise ValueError("Un membre ne peut participer qu'une seule fois à une dépense.")
    part, reste = divmod(montant_centimes, len(participants))
    return {membre_id: part + (reste if ordre == 0 else 0) for ordre, membre_id in enumerate(participants)}


def _valider_depense(conn, groupe_id, libelle, montant_centimes, date_depense, payeur_id, participants):
    groupe = obtenir_groupe(conn, groupe_id)
    libelle = _texte_non_vide(libelle, "Le libellé")
    parts = repartir_centimes(montant_centimes, participants)
    membres = {membre["id"] for membre in lister_membres(conn, groupe_id)}
    if type(payeur_id) is not int or payeur_id not in membres:
        raise ValueError("Le payeur doit appartenir au groupe.")
    if not set(parts).issubset(membres):
        raise ValueError("Tous les participants doivent appartenir au groupe.")
    jour = _date_iso(date_depense)
    if not groupe["date_debut"] <= jour <= groupe["date_fin"]:
        raise ValueError("La date de la dépense doit être comprise dans le séjour, bornes incluses.")
    return libelle, jour, list(parts)


def ajouter_depense(conn, groupe_id, libelle, montant_centimes, date_depense, payeur_id, participants):
    with conn:
        libelle, jour, participants = _valider_depense(
            conn, groupe_id, libelle, montant_centimes, date_depense, payeur_id, participants
        )
        curseur = conn.execute(
            "INSERT INTO depenses (groupe_id, libelle, montant_centimes, date, payeur_id) VALUES (?, ?, ?, ?, ?)",
            (groupe_id, libelle, montant_centimes, jour, payeur_id),
        )
        depense_id = curseur.lastrowid
        conn.executemany(
            "INSERT INTO participants (depense_id, membre_id, ordre) VALUES (?, ?, ?)",
            [(depense_id, membre_id, ordre) for ordre, membre_id in enumerate(participants)],
        )
    return depense_id


def lister_depenses(conn, groupe_id):
    obtenir_groupe(conn, groupe_id)
    depenses = [dict(ligne) for ligne in conn.execute(
        "SELECT d.*, m.nom AS payeur FROM depenses d JOIN membres m ON m.id = d.payeur_id "
        "WHERE d.groupe_id = ? ORDER BY d.date DESC, d.id DESC", (groupe_id,)
    )]
    participants = conn.execute(
        "SELECT p.*, m.nom FROM participants p JOIN membres m ON m.id = p.membre_id "
        "JOIN depenses d ON d.id = p.depense_id WHERE d.groupe_id = ? ORDER BY p.depense_id, p.ordre",
        (groupe_id,),
    ).fetchall()
    par_depense = {}
    for participant in participants:
        par_depense.setdefault(participant["depense_id"], []).append(dict(participant))
    for depense in depenses:
        depense["participants"] = par_depense.get(depense["id"], [])
        parts = repartir_centimes(depense["montant_centimes"], [p["membre_id"] for p in depense["participants"]])
        for participant in depense["participants"]:
            participant["part_centimes"] = parts[participant["membre_id"]]
    return depenses


def obtenir_depense(conn, groupe_id, depense_id):
    depense = conn.execute(
        "SELECT * FROM depenses WHERE id = ? AND groupe_id = ?", (depense_id, groupe_id)
    ).fetchone()
    if depense is None:
        raise ValueError("Cette dépense n'existe pas dans le groupe sélectionné.")
    return depense


def supprimer_depense(conn, groupe_id, depense_id):
    with conn:
        obtenir_depense(conn, groupe_id, depense_id)
        conn.execute("DELETE FROM depenses WHERE id = ? AND groupe_id = ?", (depense_id, groupe_id))


def modifier_depense(conn, groupe_id, depense_id, libelle, montant_centimes, date_depense, payeur_id, participants):
    """Remplace une dépense et ses participants dans une seule transaction."""
    with conn:
        obtenir_depense(conn, groupe_id, depense_id)
        libelle, jour, participants = _valider_depense(
            conn, groupe_id, libelle, montant_centimes, date_depense, payeur_id, participants
        )
        conn.execute(
            "UPDATE depenses SET libelle = ?, montant_centimes = ?, date = ?, payeur_id = ? "
            "WHERE id = ? AND groupe_id = ?",
            (libelle, montant_centimes, jour, payeur_id, depense_id, groupe_id),
        )
        conn.execute("DELETE FROM participants WHERE depense_id = ?", (depense_id,))
        conn.executemany(
            "INSERT INTO participants (depense_id, membre_id, ordre) VALUES (?, ?, ?)",
            [(depense_id, membre_id, ordre) for ordre, membre_id in enumerate(participants)],
        )


def filtrer_depenses(depenses, membre_id=None, date_debut=None, date_fin=None):
    """Filtre les dépenses payées ou partagées par un membre, bornes incluses."""
    debut = _date_iso(date_debut) if date_debut is not None else None
    fin = _date_iso(date_fin) if date_fin is not None else None
    if debut and fin and fin < debut:
        raise ValueError("La fin du filtre ne peut pas précéder son début.")
    return [
        d for d in depenses
        if (debut is None or d["date"] >= debut)
        and (fin is None or d["date"] <= fin)
        and (membre_id is None or d["payeur_id"] == membre_id
             or any(p["membre_id"] == membre_id for p in d["participants"]))
    ]


def exporter_csv(depenses):
    """Produit un CSV français ; les textes ne deviennent pas des formules Excel."""
    def texte(valeur):
        return "'" + valeur if valeur.lstrip().startswith(("=", "+", "-", "@")) else valeur

    sortie = StringIO(newline="")
    ecrivain = csv.writer(sortie, delimiter=";")
    ecrivain.writerow(["Date", "Libellé", "Montant (€)", "Payeur", "Participants (ordre)"])
    for depense in depenses:
        montant = depense["montant_centimes"]
        ecrivain.writerow([
            depense["date"], texte(depense["libelle"]), f"{montant // 100},{montant % 100:02d}",
            texte(depense["payeur"]), texte(" → ".join(p["nom"] for p in depense["participants"])),
        ])
    return sortie.getvalue().encode("utf-8-sig")


def calculer_soldes(conn, groupe_id):
    soldes = {
        membre["id"]: {"membre_id": membre["id"], "nom": membre["nom"], "paye_centimes": 0, "du_centimes": 0}
        for membre in lister_membres(conn, groupe_id)
    }
    for depense in lister_depenses(conn, groupe_id):
        soldes[depense["payeur_id"]]["paye_centimes"] += depense["montant_centimes"]
        for participant in depense["participants"]:
            soldes[participant["membre_id"]]["du_centimes"] += participant["part_centimes"]
    for solde in soldes.values():
        solde["solde_centimes"] = solde["paye_centimes"] - solde["du_centimes"]
    return list(soldes.values())
