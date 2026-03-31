
# Ce module contient toutes les fonctions CRUD (Create, Read, Update, Delete)

import sqlite3
#stockées dans un seul fichier sur le disque dur.
DB_PATH = "voodoo.db"


def _connexion(): # Ouvre et retourne une connexion à la base de données SQLite
    connexion = sqlite3.connect(DB_PATH)
    connexion.execute("PRAGMA foreign_keys = ON")
    return connexion

# Sans cette ligne, SQLite ne vérifierait pas ces liens

def creer_tables():
    connexion = _connexion()
    curseur   = connexion.cursor()
#crée un curseur — c'est l'outil qui permet d'envoyer des requêtes SQL à la base. 

    # Table des machines
    curseur.execute("""
        CREATE TABLE IF NOT EXISTS machines (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT    NOT NULL UNIQUE,
            power_w        REAL    NOT NULL DEFAULT 0,
            operator_name  TEXT,
            operator_email TEXT,
            fixed_cost     REAL    NOT NULL DEFAULT 0
        )
    """)

    # Table des produits
    curseur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT    NOT NULL UNIQUE
        )
    """)

    # Table des étapes 
    curseur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id   INTEGER NOT NULL,
            machine_id   INTEGER,
            duration_min INTEGER NOT NULL,
            step_order   INTEGER NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
            FOREIGN KEY (machine_id) REFERENCES machines(id) ON DELETE SET NULL
        )
    """)

    # Table des commandes journalières
    curseur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id           INTEGER NOT NULL,
            start_time           TEXT    NOT NULL,
            order_date           TEXT    NOT NULL,
            electricity_price_id INTEGER,
            FOREIGN KEY (product_id)           REFERENCES products(id),
            FOREIGN KEY (electricity_price_id) REFERENCES electricity_prices(id)
        )
    """)

    # Table des prix d'électricité (cache ENTSO-E)
    curseur.execute("""
        CREATE TABLE IF NOT EXISTS electricity_prices (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            date          TEXT    NOT NULL,
            hour_ts       TEXT    NOT NULL,
            price_eur_mwh REAL    NOT NULL,
            UNIQUE(date, hour_ts)
        )
    """)

    connexion.commit()
    connexion.close()
# commit() valide et écrit toutes les modifications dans le fichier. Sans cette ligne,
#  toutes les tables créées seraient perdues à la fermeture
# close() ferme proprement la connexion et libère les ressources système

# ==============================================================================
# MACHINES
# ==============================================================================

def ajouter_machine(name, power_w, operator_name, operator_email, fixed_cost):
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute(
        "INSERT INTO machines (name, power_w, operator_name, operator_email, fixed_cost) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, power_w, operator_name, operator_email, fixed_cost)
    )
    connexion.commit()
    nouvel_id = curseur.lastrowid # après l'insertion, SQLite attribue automatiquement un id
    connexion.close()
    return nouvel_id


def lister_machines(): # Retourne toutes les machines enregistrées dans la base, triées par nom
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute(
        "SELECT id, name, power_w, operator_name, operator_email, fixed_cost "
        "FROM machines ORDER BY name"
    )
    lignes = curseur.fetchall() #récupère toutes les lignes du résultat en une seule fois sous forme de liste de tuples.
    connexion.close()
    return lignes


def trouver_machine(machine_id):
    """Retourne une machine par son id, ou None si inexistante."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute(
        "SELECT id, name, power_w, operator_name, operator_email, fixed_cost "
        "FROM machines WHERE id=?",
        (machine_id,)
    )
    ligne = curseur.fetchone() #, récupère une seule ligne 
    connexion.close()
    return ligne


def modifier_machine(machine_id, name, power_w, operator_name, operator_email, fixed_cost):
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute(
        "UPDATE machines SET name=?, power_w=?, operator_name=?, operator_email=?, fixed_cost=? "
        "WHERE id=?",
        (name, power_w, operator_name, operator_email, fixed_cost, machine_id)
    )
    connexion.commit()
    connexion.close()

# WHERE id=? : très important — sans cette condition, toutes les machines seraient modifiées. Ici on cible uniquement la machine dont l'id correspond


def supprimer_machine(machine_id): # Supprime une machine de la base par son id
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("DELETE FROM machines WHERE id=?", (machine_id,))
    connexion.commit()
    connexion.close()


# ==============================================================================
# PRODUCTS
# ==============================================================================

def ajouter_produit(name):
    """Insère un nouveau produit. Retourne l'id généré."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("INSERT INTO products (name) VALUES (?)", (name,))
    connexion.commit()
    nouvel_id = curseur.lastrowid
    connexion.close()
    return nouvel_id


def modifier_produit(product_id, name):
    """Renomme un produit existant."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("UPDATE products SET name=? WHERE id=?", (name, product_id))
    connexion.commit()
    connexion.close()


def lister_produits():
    """Retourne tous les produits : (id, name)."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("SELECT id, name FROM products ORDER BY name")
    lignes = curseur.fetchall()
    connexion.close()
    return lignes


def supprimer_produit(product_id):
    """Supprime un produit et toutes ses étapes (CASCADE)."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("DELETE FROM tasks   WHERE product_id=?", (product_id,))
    curseur.execute("DELETE FROM products WHERE id=?",        (product_id,))
    connexion.commit()
    connexion.close()


# ==============================================================================
# TASKS (étapes)
# ==============================================================================

def ajouter_etape(product_id, machine_id, duration_min, step_order):
    """Insère une étape dans un produit."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute(
        "INSERT INTO tasks (product_id, machine_id, duration_min, step_order) VALUES (?,?,?,?)",
        (product_id, machine_id, duration_min, step_order)
    )
    connexion.commit()
    connexion.close() 


def lister_etapes_produit(product_id):
    """
    Retourne les étapes d'un produit, triées par step_order.
    Chaque ligne : (id, step_order, machine_name, duration_min, machine_id,
                    power_w, operator_name, operator_email, fixed_cost)
    """
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("""
        SELECT t.id,
               t.step_order,
               m.name,
               t.duration_min,
               t.machine_id,
               m.power_w,
               m.operator_name,
               m.operator_email,
               m.fixed_cost
        FROM tasks t
        JOIN machines m ON t.machine_id = m.id
        WHERE t.product_id = ?
        ORDER BY t.step_order
    """, (product_id,))
    lignes = curseur.fetchall()
    connexion.close()
    return lignes


def prochain_ordre_etape(product_id):
    """Retourne le prochain numéro d'ordre disponible pour un produit."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("SELECT COALESCE(MAX(step_order), 0) + 1 FROM tasks WHERE product_id=?", (product_id,))
    resultat = curseur.fetchone()[0]
    connexion.close()
    return resultat
#`MAX(step_order)` : cherche le **numéro d'ordre le plus élevé** parmi les étapes existantes
# - `COALESCE(MAX(step_order), 0)` : si le produit n'a encore aucune étape, `MAX` retourne `NULL`. `COALESCE` le remplace par `0`
# - `+ 1` : on ajoute 1 pour obtenir le prochain numéro


def supprimer_etape(task_id):
    """Supprime une étape par son id."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    connexion.commit()
    connexion.close()


# ==============================================================================
# ORDERS (commandes)
# ==============================================================================

def ajouter_commande(product_id, start_time, order_date, electricity_price_id=None):
    """Insère une commande. Retourne l'id généré."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute(
        "INSERT INTO orders (product_id, start_time, order_date, electricity_price_id) VALUES (?,?,?,?)",
        (product_id, start_time, order_date, electricity_price_id)
    )
    connexion.commit()
    nouvel_id = curseur.lastrowid
    connexion.close()
    return nouvel_id


def modifier_commande(order_id, electricity_price_id):
    """Met à jour l'electricity_price_id d'une commande."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute(
        "UPDATE orders SET electricity_price_id=? WHERE id=?",
        (electricity_price_id, order_id)
    )
    connexion.commit()
    connexion.close()


def trouver_id_prix_electricite(date_str, horodatage_iso):
    """
    Retourne l'id du prix d'électricité correspondant à l'instant donné
    (dernier intervalle dont l'heure de début est <= horodatage_iso).
    Retourne None si aucun prix n'existe pour cette date.
    """
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute(
        "SELECT id FROM electricity_prices "
        "WHERE date=? AND hour_ts <= ? "
        "ORDER BY hour_ts DESC LIMIT 1",
        (date_str, horodatage_iso)
    )
    ligne = curseur.fetchone()
    connexion.close()
    return ligne[0] if ligne else None

#ligne[0] if ligne else None : si on a trouvé un résultat, on retourne son id. Sinon on retourne None

def lister_commandes_du_jour(order_date):
    """
    Retourne les commandes d'une date donnée (format 'YYYY-MM-DD'), triées par heure.
    Chaque ligne : (id, product_name, start_time, product_id)
    """
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("""
        SELECT o.id, p.name, o.start_time, o.product_id
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.order_date = ?
        ORDER BY o.start_time
    """, (order_date,))
    lignes = curseur.fetchall()
    connexion.close()
    return lignes


def supprimer_commande(order_id):
    """Supprime une commande par son id."""
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute("DELETE FROM orders WHERE id=?", (order_id,))
    connexion.commit()
    connexion.close()


# ==============================================================================
# ELECTRICITY_PRICES (cache des prix ENTSO-E)
# ==============================================================================

def sauvegarder_prix_electricite(date_str, serie_prix):
    """
    Stocke ou met à jour les prix d'électricité pour une date donnée.
    serie_prix : pandas.Series indexé par Timestamp (Europe/Brussels).
    date_str   : 'YYYY-MM-DD'
    """
    connexion = _connexion()
    curseur   = connexion.cursor()
    for horodatage, prix in serie_prix.items(): #on parcourt la Series pandas. À chaque tour,
        curseur.execute(
            "INSERT OR REPLACE INTO electricity_prices (date, hour_ts, price_eur_mwh) "
            "VALUES (?, ?, ?)",
            (date_str, horodatage.isoformat(), float(prix)) #horodatage est une heure et prix est le prix correspondant
        )
    connexion.commit()
    connexion.close()


def charger_prix_electricite(date_str):
    """
    Retourne les prix stockés pour une date sous forme de pandas.Series,
    ou None si aucune donnée n'existe pour cette date.
    date_str : 'YYYY-MM-DD'
    """
    import pandas
    connexion = _connexion()
    curseur   = connexion.cursor()
    curseur.execute(
        "SELECT hour_ts, price_eur_mwh FROM electricity_prices WHERE date=? ORDER BY hour_ts",
        (date_str,)
    )
    lignes = curseur.fetchall()
    connexion.close()
    if not lignes:
        return None
    index_temporel = pandas.to_datetime([ligne[0] for ligne in lignes], utc=True) #reconstruit l'index temporel en convertissant chaque texte stocké en vrai timestamp pandas
    valeurs        = [ligne[1] for ligne in lignes] 
    return pandas.Series(valeurs, index=index_temporel)
