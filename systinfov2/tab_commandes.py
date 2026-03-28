import os
import importlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QTableWidgetItem, QMessageBox, QHeaderView
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal

import database as db
import api_entsoe
import email_sender

_TZ_CET = ZoneInfo("Europe/Brussels")
_UI_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


class EmailWorker(QThread):
    finished = pyqtSignal(int, list)

    def __init__(self, schedules, order_date):
        super().__init__()
        self.schedules  = schedules
        self.order_date = order_date

    def run(self):
        sent, errors = 0, []
        for (op_name, op_email), lines in self.schedules.items():
            if not op_email:
                continue
            subject = f"Planning de production du {self.order_date}"
            body    = email_sender.build_operator_schedule(op_name, lines)
            try:
                if email_sender.send_email(op_email, subject, body):
                    sent += 1
                else:
                    errors.append(f"{op_name} <{op_email}> : échec inconnu")
            except Exception as e:
                errors.append(f"{op_name} <{op_email}> : {e}")
        self.finished.emit(sent, errors)


class SimpleEmailWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, to_email, subject, body):
        super().__init__()
        self.to_email = to_email
        self.subject  = subject
        self.body     = body

    def run(self):
        try:
            ok = email_sender.send_email(self.to_email, self.subject, self.body)
            self.finished.emit(ok, "" if ok else "Échec inconnu")
        except Exception as e:
            self.finished.emit(False, str(e))


class OrdersTab(QWidget):

    def __init__(self, prices_tab, get_manager_info=None):
        super().__init__()
        self._prices_tab       = prices_tab
        self._get_manager_info = get_manager_info
        uic.loadUi(os.path.join(_UI_DIR, "orders_tab.ui"), self)
        self.date_order.setDate(QDate.currentDate())
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        font = self.lbl_total.font()
        font.setBold(True)
        self.lbl_total.setFont(font)
        self.btn_add_order.clicked.connect(self._add_order)
        self.btn_delete.clicked.connect(self._delete_order)
        self.btn_calc.clicked.connect(self._calculate_costs)
        self.btn_email.clicked.connect(self._send_emails)
        self.btn_refresh.clicked.connect(self._refresh_orders)
        self.pushButton.clicked.connect(self._on_push_button)
        self._refresh_orders()

    def _on_push_button(self):
        """Action du nouveau bouton ajouté via Qt Designer."""
        QMessageBox.information(self, "Nouveau bouton", "Ce bouton est prêt à être configuré !")

    def refresh_product_combo(self):
        self.cmb_product.clear()
        for p_id, p_name in db.select_products():
            self.cmb_product.addItem(p_name, p_id)

    def _refresh_orders(self):
        self.table.setRowCount(0)
        order_date = self.date_order.date().toString("yyyy-MM-dd")
        for row in db.select_orders_for_date(order_date):
            o_id, p_name, start_time, p_id = row
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(p_name))
            self.table.setItem(r, 1, QTableWidgetItem(start_time))
            self.table.setItem(r, 2, QTableWidgetItem("—"))
            self.table.setItem(r, 3, QTableWidgetItem("—"))
            self.table.setItem(r, 4, QTableWidgetItem(order_date))
            self.table.item(r, 0).setData(Qt.ItemDataRole.UserRole, o_id)
            self.table.item(r, 1).setData(Qt.ItemDataRole.UserRole, p_id)
        self.lbl_total.setText("")

    def _add_order(self):
        if self.cmb_product.count() == 0:
            QMessageBox.warning(self, "Aucun produit", "Ajoutez d'abord des produits dans la configuration.")
            return
        product_id = self.cmb_product.currentData()
        start_time = self.time_start.time().toString("HH:mm")
        order_date = self.date_order.date().toString("yyyy-MM-dd")
        tasks      = db.select_tasks_for_product(product_id)
        total_min  = sum(t[3] for t in tasks)
        start_dt   = datetime.strptime(f"{order_date} {start_time}", "%Y-%m-%d %H:%M")
        end_dt     = start_dt + timedelta(minutes=total_min)

        if end_dt.date() > start_dt.date():
            QMessageBox.warning(self, "Dépassement de minuit", f"Ce produit dure {total_min} min et dépasse minuit.\nChoisissez une heure de début plus tôt.")
            if self._get_manager_info:
                manager_name, manager_email = self._get_manager_info()
                if manager_email:
                    product_name = self.cmb_product.currentText()
                    subject = f"[Alerte timing] {product_name} dépasse minuit — {order_date}"
                    body = (
                        f"Bonjour {manager_name},\n\n"
                        f"La commande suivante ne sera pas terminée avant la fin de la journée :\n\n"
                        f"  Produit     : {product_name}\n"
                        f"  Date        : {order_date}\n"
                        f"  Heure début : {start_time}\n"
                        f"  Durée tot.  : {total_min} min\n"
                        f"  Fin prévue  : {end_dt.strftime('%H:%M')} (le {end_dt.strftime('%d/%m/%Y')})\n\n"
                        "La commande n'a pas été enregistrée.\n\nVoodoo Production Manager"
                    )
                    self._timing_worker = SimpleEmailWorker(manager_email, subject, body)
                    self._timing_worker.start()
            return

        db.insert_order(product_id, start_time, order_date)
        self._refresh_orders()

        if self._get_manager_info:
            manager_name, manager_email = self._get_manager_info()
            if manager_email:
                product_name = self.cmb_product.currentText()
                subject = f"[Commande] {product_name} — {order_date}"
                body = (
                    f"Bonjour {manager_name},\n\n"
                    f"Une nouvelle commande a été enregistrée :\n\n"
                    f"  Produit    : {product_name}\n"
                    f"  Date       : {order_date}\n"
                    f"  Heure début: {start_time}\n"
                    f"  Durée tot. : {total_min} min\n"
                    f"  Fin prévue : {end_dt.strftime('%H:%M')}\n\nVoodoo Production Manager"
                )
                self._order_worker = SimpleEmailWorker(manager_email, subject, body)
                self._order_worker.start()

    def _delete_order(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez une commande.")
            return
        o_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        db.delete_order(o_id)
        self._refresh_orders()

    def _calculate_costs(self):
        prices     = self._prices_tab.get_prices()
        order_date = self.date_order.date().toString("yyyy-MM-dd")
        total_cost = 0.0

        for r in range(self.table.rowCount()):
            p_id       = self.table.item(r, 1).data(Qt.ItemDataRole.UserRole)
            start_time = self.table.item(r, 1).text()
            current_dt = datetime.strptime(f"{order_date} {start_time}", "%Y-%m-%d %H:%M")
            tasks      = db.select_tasks_for_product(p_id)
            order_cost = 0.0

            for task in tasks:
                _, _, _, duration_min, _, power_w, _, _, fixed_cost = task
                energy_mwh  = (power_w / 1_000_000) * (duration_min / 60)
                price       = api_entsoe.get_price_at(prices, current_dt) if prices is not None else 0.0
                order_cost += energy_mwh * price + fixed_cost
                current_dt += timedelta(minutes=duration_min)

            start_dt      = datetime.strptime(f"{order_date} {self.table.item(r, 1).text()}", "%Y-%m-%d %H:%M")
            total_dur_min = sum(t[3] for t in tasks)
            end_time      = (start_dt + timedelta(minutes=total_dur_min)).strftime("%H:%M")
            self.table.setItem(r, 2, QTableWidgetItem(end_time))
            self.table.setItem(r, 3, QTableWidgetItem(f"{order_cost:.4f} €"))
            total_cost += order_cost

        self.lbl_total.setText(f"Coût total estimé : {total_cost:.4f} €")

        if prices is None:
            QMessageBox.information(self, "Prix non chargés", "Les prix d'électricité n'ont pas été chargés.\nLes coûts énergétiques sont calculés à 0 €/MWh.\nChargez les prix dans l'onglet « Prix Électricité ».")

    def _send_emails(self):
        order_date = self.date_order.date().toString("yyyy-MM-dd")
        orders = db.select_orders_for_date(order_date)
        if not orders:
            QMessageBox.information(self, "Aucune commande", "Aucune commande à envoyer.")
            return

        schedules: dict = {}
        for o_id, p_name, start_time, p_id in orders:
            current_dt = datetime.strptime(f"{order_date} {start_time}", "%Y-%m-%d %H:%M").replace(tzinfo=_TZ_CET)
            for task in db.select_tasks_for_product(p_id):
                _, step_order, machine_name, duration_min, _, _, op_name, op_email, _ = task
                if not op_name and not op_email:
                    current_dt += timedelta(minutes=duration_min)
                    continue
                key    = (op_name or "Inconnu", op_email or "")
                end_dt = current_dt + timedelta(minutes=duration_min)
                line   = f"{p_name} — Étape {step_order} ({machine_name}) : {current_dt.strftime('%H:%M %Z')} → {end_dt.strftime('%H:%M %Z')} ({duration_min} min)"
                schedules.setdefault(key, []).append(line)
                current_dt = end_dt

        if not schedules:
            QMessageBox.information(self, "Aucun opérateur", "Aucun opérateur n'est associé aux tâches de ces commandes.")
            return

        import config as _cfg
        importlib.reload(_cfg)
        if _cfg.EMAIL_SENDER == "votre.email@gmail.com" or _cfg.EMAIL_PASSWORD == "votre_app_password":
            QMessageBox.warning(self, "Email non configuré", "Les identifiants email sont encore des valeurs par défaut dans config.py.")
            return

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
