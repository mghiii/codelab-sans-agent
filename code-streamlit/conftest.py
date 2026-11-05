from contextlib import closing

import pytest

from base import ouvrir_base
from gestion import creer_groupe, lister_membres


@pytest.fixture(autouse=True)
def base_isolee(tmp_path, monkeypatch):
    """Même AppTest utilise une base temporaire, jamais le data.db du dépôt."""
    chemin = tmp_path / "test.db"
    monkeypatch.setenv("PARTAGE_FRAIS_DB", str(chemin))
    return chemin


@pytest.fixture
def conn(base_isolee):
    with closing(ouvrir_base(base_isolee)) as connexion:
        yield connexion


@pytest.fixture
def groupe(conn):
    groupe_id = creer_groupe(conn, "Séjour test", "2026-07-01", "2026-07-08", ["Alice", "Bob", "Chloé"])
    return groupe_id, [m["id"] for m in lister_membres(conn, groupe_id)]
