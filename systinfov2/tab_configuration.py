import os

from PyQt6 import uic
from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QTableWidgetItem, QListWidgetItem,
    QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt

import database as db

_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


class MachinesTab(QWidget):

    def __init__(self):
        super().__init__()
        self._selected_id = None
        uic.loadUi(os.path.join(_UI_DIR, "machines_tab.ui"), self)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.selectionModel().selectionChanged.connect(self._on_select)
        self.btn_add.clicked.connect(self._add)
        self.btn_update.clicked.connect(self._update)
        self.btn_delete.clicked.connect(self._delete)
        self.btn_clear.clicked.connect(self._clear_form)
        self.refresh()

    def refresh(self):
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
            self.table.item(r, 0).setData(Qt.ItemDataRole.UserRole, m_id)

    def _on_select(self):
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
        db.insert_machine(name, self.inp_power.value(), self.inp_oper.text().strip(), self.inp_email.text().strip(), self.inp_fixed.value())
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
        db.update_machine(self._selected_id, name, self.inp_power.value(), self.inp_oper.text().strip(), self.inp_email.text().strip(), self.inp_fixed.value())
        self._clear_form()
        self.refresh()

    def _delete(self):
        if self._selected_id is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez d'abord une machine.")
            return
        reply = QMessageBox.question(self, "Confirmer", "Supprimer cette machine ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
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


class ProductsTab(QWidget):

    def __init__(self):
        super().__init__()
        self._current_product_id = None
        uic.loadUi(os.path.join(_UI_DIR, "products_tab.ui"), self)
        self.table_tasks.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.list_products.currentItemChanged.connect(self._on_product_select)
        self.btn_add_prod.clicked.connect(self._add_product)
        self.btn_ren_prod.clicked.connect(self._rename_product)
        self.btn_del_prod.clicked.connect(self._delete_product)
        self.btn_add_step.clicked.connect(self._add_task)
        self.btn_del_step.clicked.connect(self._delete_task)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.refresh_products()

    def refresh_products(self):
        self.list_products.clear()
        for p_id, p_name in db.select_products():
            item = QListWidgetItem(p_name)
            item.setData(Qt.ItemDataRole.UserRole, p_id)
            self.list_products.addItem(item)

    def _on_product_select(self, current, _previous):
        if current is None:
            self._current_product_id = None
            self.table_tasks.setRowCount(0)
            self.inp_prod_name.clear()
            return
        self._current_product_id = current.data(Qt.ItemDataRole.UserRole)
        self.inp_prod_name.setText(current.text())
        self._refresh_tasks()

    def _add_product(self):
        name = self.inp_prod_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Champ manquant", "Entrez un nom de produit.")
            return
        db.insert_product(name)
        self.inp_prod_name.clear()
        self.refresh_products()

    def _rename_product(self):
        if self._current_product_id is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez d'abord un produit à renommer.")
            return
        name = self.inp_prod_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Champ manquant", "Entrez le nouveau nom du produit.")
            return
        db.update_product(self._current_product_id, name)
        self.refresh_products()

    def _delete_product(self):
        item = self.list_products.currentItem()
        if item is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez un produit.")
            return
        reply = QMessageBox.question(self, "Confirmer", f"Supprimer « {item.text()} » et toutes ses étapes ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            db.delete_product(item.data(Qt.ItemDataRole.UserRole))
            self._current_product_id = None
            self.table_tasks.setRowCount(0)
            self.refresh_products()

    def _refresh_tasks(self):
        self.table_tasks.setRowCount(0)
        if self._current_product_id is None:
            return
        for row in db.select_tasks_for_product(self._current_product_id):
            t_id, step_order, machine_name, duration_min, _, power_w, *_ = row
            r = self.table_tasks.rowCount()
            self.table_tasks.insertRow(r)
            self.table_tasks.setItem(r, 0, QTableWidgetItem(str(step_order)))
            self.table_tasks.setItem(r, 1, QTableWidgetItem(machine_name))
            self.table_tasks.setItem(r, 2, QTableWidgetItem(str(duration_min)))
            self.table_tasks.setItem(r, 3, QTableWidgetItem(str(power_w)))
            self.table_tasks.item(r, 0).setData(Qt.ItemDataRole.UserRole, t_id)

    def refresh_machine_combo(self):
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


class ConfigTab(QWidget):

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        self.machines_tab = MachinesTab()
        self.products_tab = ProductsTab()
        tabs.addTab(self.machines_tab, "Machines")
        tabs.addTab(self.products_tab, "Produits")
        tabs.currentChanged.connect(self._on_sub_tab_change)
        layout.addWidget(tabs)
        self._tabs = tabs

    def _on_sub_tab_change(self, index):
        if index == 1:
            self.products_tab.refresh_machine_combo()
            self.products_tab.refresh_products()
        if index == 0:
            self.machines_tab.refresh()
