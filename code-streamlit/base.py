import os
import sqlite3
from pathlib import Path

RACINE = Path(__file__).parent.parent
BASE = RACINE / "data.db"


def ouvrir_base(chemin=None):
    """Ouvre SQLite, charge les exemples une fois et migre l'ancien schéma.

    Un chemin explicite ou PARTAGE_FRAIS_DB permet d'isoler les tests.
    L'appelant ferme la connexion après utilisation.
    """
    chemin = chemin if chemin is not None else os.environ.get("PARTAGE_FRAIS_DB", BASE)
    conn = sqlite3.connect(chemin, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        existe = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'groupes'"
        ).fetchone()
        if not existe:
            schema = (RACINE / "base.sql").read_text(encoding="utf-8")
            conn.executescript("BEGIN IMMEDIATE;\n" + schema + "\nCOMMIT;")
        _migrer_participants(conn)
    except Exception:
        conn.rollback()
        conn.close()
        raise
    return conn


def _migrer_participants(conn):
    """Conserve les anciennes lignes et leur ordre d'insertion (rowid)."""
    colonnes = {colonne["name"] for colonne in conn.execute("PRAGMA table_info(participants)")}
    if "ordre" in colonnes:
        return
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        # Une autre connexion a pu effectuer la migration entre-temps.
        colonnes = {colonne["name"] for colonne in conn.execute("PRAGMA table_info(participants)")}
        if "ordre" not in colonnes:
            conn.execute(
                "ALTER TABLE participants ADD COLUMN ordre INTEGER NOT NULL "
                "DEFAULT 0 CHECK (ordre >= 0)"
            )
            lignes = conn.execute(
                "SELECT rowid, depense_id FROM participants ORDER BY depense_id, rowid"
            ).fetchall()
            ordres = {}
            for ligne in lignes:
                depense_id = ligne["depense_id"]
                ordre = ordres.get(depense_id, 0)
                conn.execute("UPDATE participants SET ordre = ? WHERE rowid = ?", (ordre, ligne["rowid"]))
                ordres[depense_id] = ordre + 1
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS participants_ordre_unique "
            "ON participants (depense_id, ordre)"
        )
