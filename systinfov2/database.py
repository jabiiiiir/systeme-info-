# ==============================================================================
# database.py - Gestion de la base de données SQLite
#
# Ce module contient toutes les fonctions CRUD (Create, Read, Update, Delete)
# pour les quatre tables du projet :
#   - machines   : les machines de la boulangerie
#   - products   : les produits fabriqués
#   - tasks      : les étapes de fabrication de chaque produit
#   - orders     : les commandes du jour
# ==============================================================================

import sqlite3

DB_PATH = "voodoo.db"


def _connect():
    """Ouvre une connexion SQLite et active les clés étrangères."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_all_tables():
    """Crée toutes les tables si elles n'existent pas encore."""
    conn = _connect()
    c = conn.cursor()

    # Table des machines
    c.execute("""
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT    NOT NULL UNIQUE
        )
    """)

    # Table des étapes (une étape = une machine + une durée dans un produit)
    # step_order définit l'ordre d'exécution des étapes au sein d'un produit
    c.execute("""
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
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id   INTEGER NOT NULL,
            start_time   TEXT    NOT NULL,
            order_date   TEXT    NOT NULL,
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    # Table des prix d'électricité (cache ENTSO-E)
    c.execute("""
        CREATE TABLE IF NOT EXISTS electricity_prices (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            date          TEXT    NOT NULL,
            hour_ts       TEXT    NOT NULL,
            price_eur_mwh REAL    NOT NULL,
            UNIQUE(date, hour_ts)
        )
    """)

    conn.commit()
    conn.close()


# ==============================================================================
# MACHINES
# ==============================================================================

def insert_machine(name, power_w, operator_name, operator_email, fixed_cost):
    """Insère une nouvelle machine. Retourne l'id généré."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO machines (name, power_w, operator_name, operator_email, fixed_cost) "
        "VALUES (?, ?, ?, ?, ?)",
        (name, power_w, operator_name, operator_email, fixed_cost)
    )
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id


def select_machines():
    """Retourne toutes les machines : (id, name, power_w, operator_name, operator_email, fixed_cost)."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, name, power_w, operator_name, operator_email, fixed_cost "
        "FROM machines ORDER BY name"
    )
    rows = c.fetchall()
    conn.close()
    return rows


def select_machine_by_id(machine_id):
    """Retourne une machine par son id, ou None si inexistante."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT id, name, power_w, operator_name, operator_email, fixed_cost "
        "FROM machines WHERE id=?",
        (machine_id,)
    )
    row = c.fetchone()
    conn.close()
    return row


def update_machine(machine_id, name, power_w, operator_name, operator_email, fixed_cost):
    """Met à jour les informations d'une machine existante."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "UPDATE machines SET name=?, power_w=?, operator_name=?, operator_email=?, fixed_cost=? "
        "WHERE id=?",
        (name, power_w, operator_name, operator_email, fixed_cost, machine_id)
    )
    conn.commit()
    conn.close()


def delete_machine(machine_id):
    """Supprime une machine. Les étapes qui l'utilisent passent à machine_id=NULL."""
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM machines WHERE id=?", (machine_id,))
    conn.commit()
    conn.close()


# ==============================================================================
# PRODUCTS
# ==============================================================================

def insert_product(name):
    """Insère un nouveau produit. Retourne l'id généré."""
    conn = _connect()
    c = conn.cursor()
    c.execute("INSERT INTO products (name) VALUES (?)", (name,))
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id


def select_products():
    """Retourne tous les produits : (id, name)."""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT id, name FROM products ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return rows


def delete_product(product_id):
    """Supprime un produit et toutes ses étapes (CASCADE)."""
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM tasks   WHERE product_id=?", (product_id,))
    c.execute("DELETE FROM products WHERE id=?",        (product_id,))
    conn.commit()
    conn.close()


# ==============================================================================
# TASKS (étapes)
# ==============================================================================

def insert_task(product_id, machine_id, duration_min, step_order):
    """Insère une étape dans un produit."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO tasks (product_id, machine_id, duration_min, step_order) VALUES (?,?,?,?)",
        (product_id, machine_id, duration_min, step_order)
    )
    conn.commit()
    conn.close()


def select_tasks_for_product(product_id):
    """
    Retourne les étapes d'un produit, triées par step_order.
    Chaque ligne : (id, step_order, machine_name, duration_min, machine_id,
                    power_w, operator_name, operator_email, fixed_cost)
    """
    conn = _connect()
    c = conn.cursor()
    c.execute("""
        SELECT t.id,
               t.step_order,
               COALESCE(m.name,           'Manuel / Pause'),
               t.duration_min,
               t.machine_id,
               COALESCE(m.power_w,        0),
               COALESCE(m.operator_name,  ''),
               COALESCE(m.operator_email, ''),
               COALESCE(m.fixed_cost,     0)
        FROM tasks t
        LEFT JOIN machines m ON t.machine_id = m.id
        WHERE t.product_id = ?
        ORDER BY t.step_order
    """, (product_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_next_step_order(product_id):
    """Retourne le prochain numéro d'ordre disponible pour un produit."""
    conn = _connect()
    c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(step_order), 0) + 1 FROM tasks WHERE product_id=?", (product_id,))
    result = c.fetchone()[0]
    conn.close()
    return result


def delete_task(task_id):
    """Supprime une étape par son id."""
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()


# ==============================================================================
# ORDERS (commandes)
# ==============================================================================

def insert_order(product_id, start_time, order_date):
    """Insère une commande. Retourne l'id généré."""
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "INSERT INTO orders (product_id, start_time, order_date) VALUES (?,?,?)",
        (product_id, start_time, order_date)
    )
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id


def select_orders_for_date(order_date):
    """
    Retourne les commandes d'une date donnée (format 'YYYY-MM-DD'), triées par heure.
    Chaque ligne : (id, product_name, start_time, product_id)
    """
    conn = _connect()
    c = conn.cursor()
    c.execute("""
        SELECT o.id, p.name, o.start_time, o.product_id
        FROM orders o
        JOIN products p ON o.product_id = p.id
        WHERE o.order_date = ?
        ORDER BY o.start_time
    """, (order_date,))
    rows = c.fetchall()
    conn.close()
    return rows


def delete_order(order_id):
    """Supprime une commande par son id."""
    conn = _connect()
    c = conn.cursor()
    c.execute("DELETE FROM orders WHERE id=?", (order_id,))
    conn.commit()
    conn.close()


# ==============================================================================
# ELECTRICITY_PRICES (cache des prix ENTSO-E)
# ==============================================================================

def upsert_electricity_prices(date_str, prices_series):
    """
    Stocke ou met à jour les prix d'électricité pour une date donnée.
    prices_series : pandas.Series indexé par Timestamp (Europe/Brussels).
    date_str      : 'YYYY-MM-DD'
    """
    conn = _connect()
    c = conn.cursor()
    for ts, price in prices_series.items():
        c.execute(
            "INSERT OR REPLACE INTO electricity_prices (date, hour_ts, price_eur_mwh) "
            "VALUES (?, ?, ?)",
            (date_str, ts.isoformat(), float(price))
        )
    conn.commit()
    conn.close()


def select_electricity_prices(date_str):
    """
    Retourne les prix stockés pour une date sous forme de pandas.Series,
    ou None si aucune donnée n'existe pour cette date.
    date_str : 'YYYY-MM-DD'
    """
    import pandas as pd
    conn = _connect()
    c = conn.cursor()
    c.execute(
        "SELECT hour_ts, price_eur_mwh FROM electricity_prices WHERE date=? ORDER BY hour_ts",
        (date_str,)
    )
    rows = c.fetchall()
    conn.close()
    if not rows:
        return None
    index  = pd.DatetimeIndex([pd.Timestamp(r[0]) for r in rows])
    values = [r[1] for r in rows]
    return pd.Series(values, index=index)
