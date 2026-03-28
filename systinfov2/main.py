# ==============================================================================
# main.py - Application principale PyQt6
#
# Structure des onglets :
#   1. Prix Électricité  - graphique des prix ENTSO-E du jour
#   2. Configuration     - sous-onglets Machines et Produits (CRUD)
#   3. Commandes         - planification, calcul des coûts, envoi d'emails
# ==============================================================================

import sys
import importlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_TZ_CET = ZoneInfo("Europe/Brussels")

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QComboBox, QTimeEdit, QDateEdit, QMessageBox,
    QSplitter, QGroupBox, QHeaderView, QSpinBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QTime, QDate, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import database as db
import api_entsoe
import email_sender


# ==============================================================================
# Worker threads (évitent de bloquer l'interface sur les opérations réseau)
# ==============================================================================

class PriceWorker(QThread):
    """Exécute fetch_day_ahead_prices dans un thread séparé."""
    finished = pyqtSignal(object)   # émet la Series pandas en cas de succès
    error    = pyqtSignal(str)      # émet le message d'erreur en cas d'échec

    def __init__(self, date):
        super().__init__()
        self.date = date

    def run(self):
        try:
            prices = api_entsoe.fetch_day_ahead_prices(self.date)
            self.finished.emit(prices)
        except Exception as e:
            self.error.emit(str(e))


class EmailWorker(QThread):
    """Envoie les emails dans un thread séparé."""
    # émet (nb_envoyés, liste_erreurs)
    finished = pyqtSignal(int, list)

    def __init__(self, schedules, order_date):
        super().__init__()
        self.schedules  = schedules    # {(op_name, op_email): [lignes]}
        self.order_date = order_date

    def run(self):
        sent   = 0
        errors = []
        for (op_name, op_email), lines in self.schedules.items():
            if not op_email:
                continue
            subject = f"Planning de production du {self.order_date}"
            body    = email_sender.build_operator_schedule(op_name, lines)
            try:
                ok = email_sender.send_email(op_email, subject, body)
                if ok:
                    sent += 1
                else:
                    errors.append(f"{op_name} <{op_email}> : échec inconnu")
            except Exception as e:
                errors.append(f"{op_name} <{op_email}> : {e}")
        self.finished.emit(sent, errors)


# ==============================================================================
# Onglet 1 : Prix de l'électricité
# ==============================================================================

class PricesTab(QWidget):
    """
    Affiche les prix day-ahead ENTSO-E pour la Belgique sous forme de graphique.
    Un bouton permet de recharger les prix pour la date choisie.
    Alerte automatiquement si des prix négatifs sont détectés.
    """

    def __init__(self):
        super().__init__()
        self.prices = None          # pandas.Series ou None
        self._build_ui()
        # Chargement automatique des prix au démarrage (cache DB en priorité)
        QTimer.singleShot(100, self._auto_load_prices)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- Barre de contrôle (date + bouton) ---
        top = QHBoxLayout()
        top.addWidget(QLabel("Date :"))
        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True) 
        self.date_edit.setDisplayFormat("dd/MM/yyyy")   # ← ajoute cette ligne
        self.date_edit.setMinimumWidth(130)              # ← et cette ligne
        top.addWidget(self.date_edit)
        top.addWidget(self.date_edit)

        self.btn_load = QPushButton("Charger les prix")
        self.btn_load.clicked.connect(self.load_prices)
        top.addWidget(self.btn_load)
        top.addStretch()
        layout.addLayout(top)

        # --- Zone d'information (prix min / max / négatifs) ---
        self.lbl_info = QLabel("Cliquez sur « Charger les prix » pour afficher les données.")
        self.lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_info)

        # --- Graphique matplotlib ---
        self.figure = Figure(figsize=(8, 4))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

    def _auto_load_prices(self):
        """
        Au démarrage : charge les prix depuis le cache DB.
        Si absent, lance un appel API automatique pour la date du jour.
        """
        qdate    = self.date_edit.date()
        date_str = qdate.toString("yyyy-MM-dd")
        cached   = db.select_electricity_prices(date_str)
        if cached is not None:
            self.prices = cached
            self.lbl_info.setText("Prix chargés depuis le cache local.")
            self._draw_chart()
        else:
            self.load_prices()

    def load_prices(self):
        """Lance le chargement des prix dans un thread séparé pour ne pas bloquer l'interface."""
        qdate  = self.date_edit.date()
        target = datetime(qdate.year(), qdate.month(), qdate.day())

        self.btn_load.setEnabled(False)
        self.lbl_info.setText("Chargement en cours…")

        self._worker = PriceWorker(target)
        self._worker.finished.connect(self._on_prices_loaded)
        self._worker.error.connect(self._on_prices_error)
        self._worker.start()

    def _on_prices_loaded(self, prices):
        self.prices = prices
        # Sauvegarde en base de données pour réutilisation future
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        db.upsert_electricity_prices(date_str, prices)
        self.btn_load.setEnabled(True)
        self._draw_chart()
        self._check_negative_prices()

    def _on_prices_error(self, message):
        self.btn_load.setEnabled(True)
        self.lbl_info.setText("Échec du chargement.")
        QMessageBox.critical(self, "Erreur API", f"Impossible de récupérer les prix :\n{message}")

    def _draw_chart(self):
        """Trace le graphique des prix EUR/MWh sur la journée."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        times  = self.prices.index.to_pydatetime()
        values = self.prices.values

        # Colore en rouge les barres à prix négatif
        colors = ["#e74c3c" if v < 0 else "#2ecc71" for v in values]
        ax.bar(range(len(values)), values, color=colors, width=0.8)
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")

        # Étiquettes de l'axe X (heures)
        step = max(1, len(times) // 12)
        ax.set_xticks(range(0, len(times), step))
        ax.set_xticklabels(
            [t.strftime("%H:%M") for t in times[::step]],
            rotation=45, ha="right", fontsize=8
        )

        ax.set_ylabel("EUR / MWh")
        ax.set_title(f"Prix day-ahead — {self.date_edit.date().toString('dd/MM/yyyy')}")
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        self.figure.tight_layout()
        self.canvas.draw()

        # Mise à jour du texte d'information
        mn = float(self.prices.min())
        mx = float(self.prices.max())
        neg_count = int((self.prices < 0).sum())
        info = f"Min : {mn:.2f} €/MWh   |   Max : {mx:.2f} €/MWh   |   Heures négatives : {neg_count}"
        self.lbl_info.setText(info)

    def _check_negative_prices(self):
        """Affiche une alerte si des prix négatifs existent."""
        neg = api_entsoe.get_negative_prices(self.prices)
        if not neg.empty:
            hours = ", ".join(t.strftime("%H:%M") for t in neg.index.to_pydatetime())
            QMessageBox.warning(
                self, "Prix négatifs détectés",
                f"Des prix négatifs ont été détectés aux heures suivantes :\n{hours}\n\n"
                "C'est le moment idéal pour planifier vos productions énergivores !"
            )

    def get_prices(self):
        """Retourne la Series des prix (peut être None si pas encore chargée)."""
        return self.prices


# ==============================================================================
# Onglet Configuration / Sous-onglet Machines
# ==============================================================================

class MachinesTab(QWidget):
    """
    Gestion CRUD des machines.
    La liste affiche toutes les machines ; le formulaire permet d'en ajouter,
    modifier ou supprimer.
    """

    def __init__(self):
        super().__init__()
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QHBoxLayout(self)

        # --- Tableau des machines ---
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Nom", "Puissance (W)", "Opérateur", "Email opérateur", "Coût fixe (€)"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.selectionModel().selectionChanged.connect(self._on_select)
        layout.addWidget(self.table, 2)

        # --- Formulaire d'édition ---
        form_box = QGroupBox("Détails de la machine")
        form_layout = QFormLayout(form_box)

        self.inp_name    = QLineEdit()
        self.inp_power   = QDoubleSpinBox()
        self.inp_power.setRange(0, 100_000)
        self.inp_power.setSuffix(" W")
        self.inp_oper    = QLineEdit()
        self.inp_email   = QLineEdit()
        self.inp_fixed   = QDoubleSpinBox()
        self.inp_fixed.setRange(0, 10_000)
        self.inp_fixed.setSuffix(" €")
        self.inp_fixed.setDecimals(2)

        form_layout.addRow("Nom :",             self.inp_name)
        form_layout.addRow("Puissance (W) :",   self.inp_power)
        form_layout.addRow("Opérateur :",       self.inp_oper)
        form_layout.addRow("Email opérateur :", self.inp_email)
        form_layout.addRow("Coût fixe (€) :",   self.inp_fixed)

        btn_add    = QPushButton("Ajouter")
        btn_update = QPushButton("Modifier")
        btn_delete = QPushButton("Supprimer")
        btn_clear  = QPushButton("Effacer")

        btn_add.clicked.connect(self._add)
        btn_update.clicked.connect(self._update)
        btn_delete.clicked.connect(self._delete)
        btn_clear.clicked.connect(self._clear_form)

        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_update)
        btn_row.addWidget(btn_delete)
        btn_row.addWidget(btn_clear)

        form_v = QVBoxLayout()
        form_v.addWidget(form_box)
        form_v.addLayout(btn_row)
        form_v.addStretch()

        layout.addLayout(form_v, 1)

        self._selected_id = None    # id de la machine sélectionnée

    # --- Rafraîchissement ---

    def refresh(self):
        """Recharge toutes les machines depuis la base de données."""
        self.table.setRowCount(0)
        for row in db.select_machines():
            m_id, name, power, oper, email, fixed = row
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(name))
            self.table.setItem(r, 1, QTableWidgetItem(str(power)))
            self.table.setItem(r, 2, QTableWidgetItem(oper or ""))
            self.table.setItem(r, 3, QTableWidgetItem(email or ""))
            self.table.setItem(r, 4, QTableWidgetItem(str(fixed)))
            # Stocke l'id dans la première colonne (données utilisateur)
            self.table.item(r, 0).setData(Qt.ItemDataRole.UserRole, m_id)

    # --- Événements ---

    def _on_select(self):
        """Remplit le formulaire avec la machine sélectionnée."""
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        r = rows[0].row()
        self._selected_id = self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
        self.inp_name.setText(self.table.item(r, 0).text())
        self.inp_power.setValue(float(self.table.item(r, 1).text()))
        self.inp_oper.setText(self.table.item(r, 2).text())
        self.inp_email.setText(self.table.item(r, 3).text())
        self.inp_fixed.setValue(float(self.table.item(r, 4).text()))

    def _add(self):
        name = self.inp_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Champ manquant", "Le nom est obligatoire.")
            return
        db.insert_machine(
            name, self.inp_power.value(),
            self.inp_oper.text().strip(),
            self.inp_email.text().strip(),
            self.inp_fixed.value()
        )
        self._clear_form()
        self.refresh()

    def _update(self):
        if self._selected_id is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez d'abord une machine.")
            return
        name = self.inp_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Champ manquant", "Le nom est obligatoire.")
            return
        db.update_machine(
            self._selected_id, name, self.inp_power.value(),
            self.inp_oper.text().strip(),
            self.inp_email.text().strip(),
            self.inp_fixed.value()
        )
        self._clear_form()
        self.refresh()

    def _delete(self):
        if self._selected_id is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez d'abord une machine.")
            return
        reply = QMessageBox.question(
            self, "Confirmer", "Supprimer cette machine ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_machine(self._selected_id)
            self._clear_form()
            self.refresh()

    def _clear_form(self):
        self._selected_id = None
        self.inp_name.clear()
        self.inp_power.setValue(0)
        self.inp_oper.clear()
        self.inp_email.clear()
        self.inp_fixed.setValue(0)
        self.table.clearSelection()


# ==============================================================================
# Onglet Configuration / Sous-onglet Produits
# ==============================================================================

class ProductsTab(QWidget):
    """
    Gestion CRUD des produits et de leurs étapes (recette de fabrication).
    - Partie gauche  : liste des produits
    - Partie droite  : tableau des étapes du produit sélectionné
    - Formulaire bas : ajouter / supprimer des étapes
    """

    def __init__(self):
        super().__init__()
        self._current_product_id = None
        self._build_ui()
        self.refresh_products()

    def _build_ui(self):
        main = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # === Panneau gauche : produits ===
        left = QWidget()
        lv = QVBoxLayout(left)

        lv.addWidget(QLabel("Produits :"))
        self.list_products = QListWidget()
        self.list_products.currentItemChanged.connect(self._on_product_select)
        lv.addWidget(self.list_products)

        # Formulaire d'ajout de produit
        p_form = QHBoxLayout()
        self.inp_prod_name = QLineEdit()
        self.inp_prod_name.setPlaceholderText("Nom du nouveau produit")
        btn_add_prod = QPushButton("Ajouter")
        btn_del_prod = QPushButton("Supprimer")
        btn_add_prod.clicked.connect(self._add_product)
        btn_del_prod.clicked.connect(self._delete_product)
        p_form.addWidget(self.inp_prod_name)
        p_form.addWidget(btn_add_prod)
        p_form.addWidget(btn_del_prod)
        lv.addLayout(p_form)

        splitter.addWidget(left)

        # === Panneau droit : étapes ===
        right = QWidget()
        rv = QVBoxLayout(right)

        rv.addWidget(QLabel("Étapes du produit sélectionné :"))
        self.table_tasks = QTableWidget(0, 4)
        self.table_tasks.setHorizontalHeaderLabels(
            ["Ordre", "Machine", "Durée (min)", "Puissance (W)"]
        )
        self.table_tasks.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_tasks.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        rv.addWidget(self.table_tasks)

        # Formulaire d'ajout d'une étape
        step_box = QGroupBox("Ajouter une étape")
        sf = QFormLayout(step_box)

        self.cmb_machine  = QComboBox()
        self.spn_duration = QSpinBox()
        self.spn_duration.setRange(1, 9999)
        self.spn_duration.setSuffix(" min")

        sf.addRow("Machine :",       self.cmb_machine)
        sf.addRow("Durée (min) :",   self.spn_duration)

        btn_add_step = QPushButton("Ajouter l'étape")
        btn_del_step = QPushButton("Supprimer l'étape sélectionnée")
        btn_add_step.clicked.connect(self._add_task)
        btn_del_step.clicked.connect(self._delete_task)

        step_btns = QHBoxLayout()
        step_btns.addWidget(btn_add_step)
        step_btns.addWidget(btn_del_step)

        rv.addWidget(step_box)
        rv.addLayout(step_btns)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main.addWidget(splitter)

    # --- Produits ---

    def refresh_products(self):
        """Recharge la liste des produits."""
        self.list_products.clear()
        for p_id, p_name in db.select_products():
            item = QListWidgetItem(p_name)
            item.setData(Qt.ItemDataRole.UserRole, p_id)
            self.list_products.addItem(item)

    def _on_product_select(self, current, _previous):
        if current is None:
            self._current_product_id = None
            self.table_tasks.setRowCount(0)
            return
        self._current_product_id = current.data(Qt.ItemDataRole.UserRole)
        self._refresh_tasks()

    def _add_product(self):
        name = self.inp_prod_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Champ manquant", "Entrez un nom de produit.")
            return
        db.insert_product(name)
        self.inp_prod_name.clear()
        self.refresh_products()

    def _delete_product(self):
        item = self.list_products.currentItem()
        if item is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez un produit.")
            return
        reply = QMessageBox.question(
            self, "Confirmer",
            f"Supprimer « {item.text()} » et toutes ses étapes ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_product(item.data(Qt.ItemDataRole.UserRole))
            self._current_product_id = None
            self.table_tasks.setRowCount(0)
            self.refresh_products()

    # --- Étapes ---

    def _refresh_tasks(self):
        """Recharge les étapes du produit courant."""
        self.table_tasks.setRowCount(0)
        if self._current_product_id is None:
            return
        for row in db.select_tasks_for_product(self._current_product_id):
            # (id, step_order, machine_name, duration_min, machine_id, power_w, ...)
            t_id, step_order, machine_name, duration_min, _, power_w, *_ = row
            r = self.table_tasks.rowCount()
            self.table_tasks.insertRow(r)
            self.table_tasks.setItem(r, 0, QTableWidgetItem(str(step_order)))
            self.table_tasks.setItem(r, 1, QTableWidgetItem(machine_name))
            self.table_tasks.setItem(r, 2, QTableWidgetItem(str(duration_min)))
            self.table_tasks.setItem(r, 3, QTableWidgetItem(str(power_w)))
            # Stocke l'id de l'étape pour la suppression
            self.table_tasks.item(r, 0).setData(Qt.ItemDataRole.UserRole, t_id)

    def refresh_machine_combo(self):
        """Recharge le combo de sélection de machine (appelé depuis MainWindow)."""
        self.cmb_machine.clear()
        self.cmb_machine.addItem("Manuel / Pause", None)
        for m_id, m_name, *_ in db.select_machines():
            self.cmb_machine.addItem(m_name, m_id)

    def _add_task(self):
        if self._current_product_id is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez d'abord un produit.")
            return
        machine_id = self.cmb_machine.currentData()
        duration   = self.spn_duration.value()
        step_order = db.get_next_step_order(self._current_product_id)
        db.insert_task(self._current_product_id, machine_id, duration, step_order)
        self._refresh_tasks()

    def _delete_task(self):
        rows = self.table_tasks.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez une étape à supprimer.")
            return
        t_id = self.table_tasks.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        db.delete_task(t_id)
        self._refresh_tasks()


# ==============================================================================
# Onglet Configuration (conteneur des 2 sous-onglets)
# ==============================================================================

class ConfigTab(QWidget):
    """Regroupe les onglets Machines et Produits dans un QTabWidget."""

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        self.machines_tab = MachinesTab()
        self.products_tab = ProductsTab()

        tabs.addTab(self.machines_tab, "Machines")
        tabs.addTab(self.products_tab, "Produits")

        # Quand on revient sur l'onglet Produits, on rafraîchit le combo de machines
        tabs.currentChanged.connect(self._on_sub_tab_change)

        layout.addWidget(tabs)
        self._tabs = tabs

    def _on_sub_tab_change(self, index):
        if index == 1:      # Onglet Produits
            self.products_tab.refresh_machine_combo()
            self.products_tab.refresh_products()
        if index == 0:      # Onglet Machines
            self.machines_tab.refresh()


# ==============================================================================
# Onglet Commandes
# ==============================================================================

class OrdersTab(QWidget):
    """
    Planification des commandes journalières.
    - Choisir un produit, une heure de début, une date
    - Afficher les commandes du jour avec leur coût estimé
    - Envoyer les emails de planning à chaque opérateur concerné
    """

    def __init__(self, prices_tab: PricesTab):
        super().__init__()
        self._prices_tab = prices_tab   # référence pour récupérer les prix chargés
        self._build_ui()
        self._refresh_orders()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- Formulaire d'ajout de commande ---
        form_box = QGroupBox("Ajouter une commande")
        form = QFormLayout(form_box)

        self.cmb_product  = QComboBox()
        self.time_start   = QTimeEdit(QTime(6, 0))
        self.time_start.setDisplayFormat("HH:mm")
        self.date_order   = QDateEdit(QDate.currentDate())
        self.date_order.setCalendarPopup(True)

        form.addRow("Produit :",       self.cmb_product)
        form.addRow("Heure de début :", self.time_start)
        form.addRow("Date :",           self.date_order)

        btn_add_order = QPushButton("Ajouter la commande")
        btn_add_order.clicked.connect(self._add_order)
        form.addRow("", btn_add_order)

        layout.addWidget(form_box)

        # --- Tableau des commandes ---
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Produit", "Heure début", "Heure fin", "Coût énergie (€)", "Date"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # --- Email supplémentaire ---
        extra_box = QGroupBox("Envoyer le planning complet à une adresse supplémentaire")
        extra_form = QFormLayout(extra_box)
        self.inp_extra_email = QLineEdit()
        self.inp_extra_email.setPlaceholderText("ex: responsable@entreprise.com (optionnel)")
        extra_form.addRow("Adresse email :", self.inp_extra_email)
        layout.addWidget(extra_box)

        # --- Boutons d'action ---
        btn_row = QHBoxLayout()

        btn_delete  = QPushButton("Supprimer la commande sélectionnée")
        btn_calc    = QPushButton("Calculer les coûts")
        self.btn_email = QPushButton("Envoyer les plannings par email")
        btn_email      = self.btn_email
        btn_refresh = QPushButton("Rafraîchir")

        btn_delete.clicked.connect(self._delete_order)
        btn_calc.clicked.connect(self._calculate_costs)
        btn_email.clicked.connect(self._send_emails)
        btn_refresh.clicked.connect(self._refresh_orders)

        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_delete)
        btn_row.addWidget(btn_calc)
        btn_row.addWidget(btn_email)
        layout.addLayout(btn_row)

        # --- Label coût total ---
        self.lbl_total = QLabel("")
        self.lbl_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        font = self.lbl_total.font()
        font.setBold(True)
        self.lbl_total.setFont(font)
        layout.addWidget(self.lbl_total)

    # --- Rafraîchissement ---

    def refresh_product_combo(self):
        """Recharge la liste des produits dans le combo."""
        self.cmb_product.clear()
        for p_id, p_name in db.select_products():
            self.cmb_product.addItem(p_name, p_id)

    def _refresh_orders(self):
        """Recharge les commandes de la date sélectionnée."""
        self.table.setRowCount(0)
        order_date = self.date_order.date().toString("yyyy-MM-dd")
        for row in db.select_orders_for_date(order_date):
            o_id, p_name, start_time, p_id = row
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(p_name))
            self.table.setItem(r, 1, QTableWidgetItem(start_time))
            self.table.setItem(r, 2, QTableWidgetItem("—"))       # fin calculée plus tard
            self.table.setItem(r, 3, QTableWidgetItem("—"))       # coût calculé plus tard
            self.table.setItem(r, 4, QTableWidgetItem(order_date))
            # Stocke les ids nécessaires
            self.table.item(r, 0).setData(Qt.ItemDataRole.UserRole, o_id)
            self.table.item(r, 1).setData(Qt.ItemDataRole.UserRole, p_id)
        self.lbl_total.setText("")

    # --- Ajout / suppression ---

    def _add_order(self):
        if self.cmb_product.count() == 0:
            QMessageBox.warning(self, "Aucun produit", "Ajoutez d'abord des produits dans la configuration.")
            return

        product_id  = self.cmb_product.currentData()
        start_time  = self.time_start.time().toString("HH:mm")
        order_date  = self.date_order.date().toString("yyyy-MM-dd")

        # Validation : la production ne doit pas dépasser minuit
        tasks = db.select_tasks_for_product(product_id)
        total_min = sum(t[3] for t in tasks)
        start_dt  = datetime.strptime(f"{order_date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt    = start_dt + timedelta(minutes=total_min)
        if end_dt.date() > start_dt.date():
            QMessageBox.warning(
                self, "Dépassement de minuit",
                f"Ce produit dure {total_min} min et dépasse minuit.\n"
                "Choisissez une heure de début plus tôt."
            )
            return

        db.insert_order(product_id, start_time, order_date)
        self._refresh_orders()

    def _delete_order(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez une commande.")
            return
        o_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        db.delete_order(o_id)
        self._refresh_orders()

    # --- Calcul des coûts ---

    def _calculate_costs(self):
        """
        Pour chaque commande, parcourt les étapes du produit et calcule :
            coût = Σ (énergie_MWh * prix_EUR_MWh + coût_fixe)
        Met à jour le tableau et affiche le total.
        """
        prices     = self._prices_tab.get_prices()
        order_date = self.date_order.date().toString("yyyy-MM-dd")
        total_cost = 0.0

        for r in range(self.table.rowCount()):
            p_id        = self.table.item(r, 1).data(Qt.ItemDataRole.UserRole)
            start_time  = self.table.item(r, 1).text()
            current_dt  = datetime.strptime(f"{order_date} {start_time}", "%Y-%m-%d %H:%M")

            tasks      = db.select_tasks_for_product(p_id)
            order_cost = 0.0

            for task in tasks:
                # (id, step_order, machine_name, duration_min, machine_id,
                #  power_w, operator_name, operator_email, fixed_cost)
                _, _, _, duration_min, _, power_w, _, _, fixed_cost = task

                energy_mwh  = (power_w / 1_000_000) * (duration_min / 60)
                price       = api_entsoe.get_price_at(prices, current_dt) if prices is not None else 0.0
                order_cost += energy_mwh * price + fixed_cost
                current_dt += timedelta(minutes=duration_min)

            # Heure de fin
            start_time_parsed = datetime.strptime(f"{order_date} {self.table.item(r, 1).text()}", "%Y-%m-%d %H:%M")
            total_dur_min = sum(t[3] for t in tasks)
            end_time = (start_time_parsed + timedelta(minutes=total_dur_min)).strftime("%H:%M")

            self.table.setItem(r, 2, QTableWidgetItem(end_time))
            self.table.setItem(r, 3, QTableWidgetItem(f"{order_cost:.4f} €"))
            total_cost += order_cost

        self.lbl_total.setText(f"Coût total estimé : {total_cost:.4f} €")

        if prices is None:
            QMessageBox.information(
                self, "Prix non chargés",
                "Les prix d'électricité n'ont pas été chargés.\n"
                "Les coûts énergétiques sont calculés à 0 €/MWh.\n"
                "Chargez les prix dans l'onglet « Prix Électricité »."
            )

    # --- Envoi des emails ---

    def _send_emails(self):
        """
        Regroupe les tâches par opérateur et envoie un email de planning à chacun.
        """
        order_date = self.date_order.date().toString("yyyy-MM-dd")
        orders = db.select_orders_for_date(order_date)

        if not orders:
            QMessageBox.information(self, "Aucune commande", "Aucune commande à envoyer.")
            return

        # Dictionnaire : {(operator_name, operator_email): [lignes de planning]}
        schedules: dict = {}

        for o_id, p_name, start_time, p_id in orders:
            current_dt = datetime.strptime(f"{order_date} {start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=_TZ_CET)
            tasks = db.select_tasks_for_product(p_id)

            for task in tasks:
                _, step_order, machine_name, duration_min, _, _, op_name, op_email, _ = task

                if not op_name and not op_email:
                    current_dt += timedelta(minutes=duration_min)
                    continue    # étape manuelle sans opérateur assigné

                key = (op_name or "Inconnu", op_email or "")
                end_dt = current_dt + timedelta(minutes=duration_min)
                line = (
                    f"{p_name} — Étape {step_order} ({machine_name}) : "
                    f"{current_dt.strftime('%H:%M %Z')} → {end_dt.strftime('%H:%M %Z')} "
                    f"({duration_min} min)"
                )
                schedules.setdefault(key, []).append(line)
                current_dt = end_dt

        if not schedules:
            QMessageBox.information(
                self, "Aucun opérateur",
                "Aucun opérateur n'est associé aux tâches de ces commandes."
            )
            return

        # Recharge config.py pour prendre en compte les modifications
        # faites pendant que l'application tourne
        import config as _cfg
        importlib.reload(_cfg)

        if _cfg.EMAIL_SENDER == "votre.email@gmail.com" or _cfg.EMAIL_PASSWORD == "votre_app_password":
            QMessageBox.warning(
                self, "Email non configuré",
                "Les identifiants email sont encore des valeurs par défaut dans config.py.\n\n"
                "Renseignez EMAIL_SENDER et EMAIL_PASSWORD,\n"
                "puis cliquez à nouveau sur Envoyer (plus besoin de redémarrer)."
            )
            return

        # Adresse supplémentaire : reçoit un résumé de toutes les tâches du jour
        extra_email = self.inp_extra_email.text().strip()
        if extra_email:
            all_lines = []
            for (op_name, _), lines in schedules.items():
                all_lines.append(f"[ {op_name} ]")
                all_lines.extend(lines)
                all_lines.append("")
            schedules[("Planning complet", extra_email)] = all_lines

        self.btn_email.setEnabled(False)
        self.btn_email.setText("Envoi en cours…")

        self._email_worker = EmailWorker(schedules, order_date)
        self._email_worker.finished.connect(self._on_emails_sent)
        self._email_worker.start()

    def _on_emails_sent(self, sent, errors):
        self.btn_email.setEnabled(True)
        self.btn_email.setText("Envoyer les plannings par email")

        msg = f"Emails envoyés avec succès : {sent}"
        if errors:
            msg += "\n\nÉchecs :\n" + "\n".join(errors)
        QMessageBox.information(self, "Résultat envoi", msg)


# ==============================================================================
# Fenêtre principale
# ==============================================================================

class MainWindow(QMainWindow):
    """
    Fenêtre principale de l'application Voodoo Production Manager.
    Initialise la base de données, pré-charge les données de démonstration,
    et assemble les trois onglets principaux.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voodoo Production Manager")
        self.resize(1100, 700)

        # Initialisation de la base de données
        db.create_all_tables()
        self._seed_demo_data()

        # Construction des onglets
        tabs = QTabWidget()

        self.prices_tab = PricesTab()
        self.config_tab = ConfigTab()
        self.orders_tab = OrdersTab(self.prices_tab)

        tabs.addTab(self.prices_tab, "Prix Électricité")
        tabs.addTab(self.config_tab, "Configuration")
        tabs.addTab(self.orders_tab, "Commandes")

        # Quand on revient sur l'onglet Commandes, on rafraîchit le combo produits
        tabs.currentChanged.connect(self._on_main_tab_change)

        self.setCentralWidget(tabs)
        self._tabs = tabs

        self._apply_stylesheet()

    def _on_main_tab_change(self, index):
        if index == 2:  # Onglet Commandes
            self.orders_tab.refresh_product_combo()
            self.orders_tab._refresh_orders()

    # --- Données de démonstration ---

    def _seed_demo_data(self):
        """
        Pré-charge 4 machines et 4 produits de boulangerie si la base est vide.
        N'insère rien si des données existent déjà.
        """
        if db.select_machines():
            return  # Des données existent déjà

        # --- Machines ---
        machines = [
            ("Pétrin industriel",        3000,  "Ahmed Benali",   "ahmed.benali@voodoo.be",   5.0),
            ("Four tunnel",              15000, "Sophie Dupont",  "sophie.dupont@voodoo.be",  20.0),
            ("Chambre de fermentation",  500,   "Ahmed Benali",   "ahmed.benali@voodoo.be",   2.0),
            ("Trancheuse-emballeuse",    800,   "Marc Lecomte",   "marc.lecomte@voodoo.be",   3.0),
        ]
        ids = {}
        for name, power, oper, email, fixed in machines:
            ids[name] = db.insert_machine(name, power, oper, email, fixed)

        # --- Produits et leurs étapes ---
        products_tasks = {
            "Pain blanc": [
                (ids["Pétrin industriel"],       20),
                (ids["Chambre de fermentation"], 60),
                (ids["Four tunnel"],             30),
                (ids["Trancheuse-emballeuse"],   10),
            ],
            "Baguette": [
                (ids["Pétrin industriel"],       15),
                (ids["Chambre de fermentation"], 45),
                (ids["Four tunnel"],             25),
            ],
            "Croissants": [
                (ids["Pétrin industriel"],       30),
                (ids["Chambre de fermentation"], 90),
                (ids["Four tunnel"],             20),
                (ids["Trancheuse-emballeuse"],    5),
            ],
            "Pain de campagne": [
                (ids["Pétrin industriel"],       25),
                (ids["Chambre de fermentation"], 75),
                (ids["Four tunnel"],             40),
            ],
        }

        for prod_name, steps in products_tasks.items():
            p_id = db.insert_product(prod_name)
            for order, (machine_id, duration) in enumerate(steps, start=1):
                db.insert_task(p_id, machine_id, duration, order)

    # --- Style visuel ---

    def _apply_stylesheet(self):
        """Applique un thème chaleureux inspiré de la boulangerie."""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #fdf6ec;
                color: #3b2a1a;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QTabWidget::pane {
                border: 1px solid #d4a96a;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #e8c99a;
                padding: 6px 16px;
                border: 1px solid #d4a96a;
                border-bottom: none;
                border-radius: 4px 4px 0 0;
            }
            QTabBar::tab:selected {
                background: #fdf6ec;
                font-weight: bold;
            }
            QPushButton {
                background-color: #c0722a;
                color: white;
                border: none;
                padding: 6px 14px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #a85c20;
            }
            QTableWidget {
                background-color: white;
                gridline-color: #e8c99a;
            }
            QHeaderView::section {
                background-color: #e8c99a;
                padding: 4px;
                border: 1px solid #d4a96a;
            }
            QGroupBox {
                border: 1px solid #d4a96a;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                font-weight: bold;
                color: #7a4010;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit {
                background-color: white;
                border: 1px solid #d4a96a;
                border-radius: 3px;
                padding: 3px 6px;
            }
            QListWidget {
                background-color: white;
                border: 1px solid #d4a96a;
            }
        """)


# ==============================================================================
# Point d'entrée
# ==============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
