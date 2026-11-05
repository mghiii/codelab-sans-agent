-- Schéma de la base : Partage de frais. Vous pouvez le modifier.
-- Les montants sont en centimes : 3000 = 30,00 €.
CREATE TABLE IF NOT EXISTS groupes (
    id INTEGER PRIMARY KEY,
    nom TEXT NOT NULL,
    date_debut TEXT NOT NULL,
    date_fin TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS membres (
    id INTEGER PRIMARY KEY,
    groupe_id INTEGER NOT NULL REFERENCES groupes(id) ON DELETE CASCADE,
    nom TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS depenses (
    id INTEGER PRIMARY KEY,
    groupe_id INTEGER NOT NULL REFERENCES groupes(id) ON DELETE CASCADE,
    libelle TEXT NOT NULL,
    montant_centimes INTEGER NOT NULL,
    date TEXT NOT NULL,
    payeur_id INTEGER NOT NULL REFERENCES membres(id)
);
CREATE TABLE IF NOT EXISTS participants (
    depense_id INTEGER NOT NULL REFERENCES depenses(id) ON DELETE CASCADE,
    membre_id INTEGER NOT NULL REFERENCES membres(id),
    ordre INTEGER NOT NULL CHECK (ordre >= 0),
    PRIMARY KEY (depense_id, membre_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS participants_ordre_unique
    ON participants (depense_id, ordre);

-- Données d'exemple, chargées à la création de data.db.
INSERT INTO groupes (id, nom, date_debut, date_fin) VALUES (1, 'Vacances à Spa', '2026-07-01', '2026-07-08');
INSERT INTO membres (id, groupe_id, nom) VALUES (1, 1, 'Alice'), (2, 1, 'Bob'), (3, 1, 'Chloé');
INSERT INTO depenses (id, groupe_id, libelle, montant_centimes, date, payeur_id) VALUES (1, 1, 'Courses', 3000, '2026-07-02', 1);
INSERT INTO participants (depense_id, membre_id, ordre) VALUES (1, 1, 0), (1, 2, 1), (1, 3, 2);
