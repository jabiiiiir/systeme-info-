import os
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import QDate, QThread, QTimer, pyqtSignal

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import database as db
import api_entsoe
import email_sender

_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")


class PriceWorker(QThread):
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, date):
        super().__init__()
        self.date = date

    def run(self):
        try:
            self.finished.emit(api_entsoe.recuperer_prix_journaliers(self.date))
        except Exception as e:
            self.error.emit(str(e))


class SimpleEmailWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, to_email, subject, body):
        super().__init__()
        self.to_email = to_email
        self.subject  = subject
        self.body     = body

    def run(self):
        try:
            ok = email_sender.envoyer_email(self.to_email, self.subject, self.body)
            self.finished.emit(ok, "" if ok else "Échec inconnu")
        except Exception as e:
            self.finished.emit(False, str(e))


class PricesTab(QWidget):

    def __init__(self, get_manager_info=None):
        super().__init__()
        self.prices = None
        self._get_manager_info = get_manager_info
        uic.loadUi(os.path.join(_UI_DIR, "prices_tab.ui"), self)
        self.date_edit.setDate(QDate.currentDate())
        self.figure = Figure(figsize=(8, 4))
        self.canvas = FigureCanvas(self.figure)
        self.canvas_container.layout().addWidget(self.canvas)
        self.btn_load.clicked.connect(self.charger_prix)
        self.btn_check_threshold.clicked.connect(self._verifier_seuil)
        QTimer.singleShot(100, self._chargement_auto_prix)

    def _chargement_auto_prix(self):
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        cached = db.charger_prix_electricite(date_str)
        if cached is not None:
            self.prices = cached
            self.lbl_info.setText("Prix chargés depuis le cache local.")
            self._dessiner_graphique()
        else:
            self.charger_prix()

    def charger_prix(self):
        qdate  = self.date_edit.date()
        target = datetime(qdate.year(), qdate.month(), qdate.day())
        self.btn_load.setEnabled(False)
        self.lbl_info.setText("Chargement en cours…")
        self._worker = PriceWorker(target)
        self._worker.finished.connect(self._prix_charges)
        self._worker.error.connect(self._erreur_chargement)
        self._worker.start()

    def _prix_charges(self, prices):
        self.prices = prices
        date_str = self.date_edit.date().toString("yyyy-MM-dd")
        db.sauvegarder_prix_electricite(date_str, prices)
        self.btn_load.setEnabled(True)
        self._dessiner_graphique()
        self._verifier_seuil()

    def _erreur_chargement(self, message):
        self.btn_load.setEnabled(True)
        self.lbl_info.setText("Échec du chargement.")
        QMessageBox.critical(self, "Erreur API", f"Impossible de récupérer les prix :\n{message}")

    def _dessiner_graphique(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        times  = self.prices.index.to_pydatetime()
        values = self.prices.values
        colors = ["#e74c3c" if v < 0 else "#2ecc71" for v in values]
        ax.bar(range(len(values)), values, color=colors, width=0.8)
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        step = max(1, len(times) // 12)
        ax.set_xticks(range(0, len(times), step))
        ax.set_xticklabels([t.strftime("%H:%M") for t in times[::step]], rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("EUR / MWh")
        ax.set_title(f"Prix day-ahead — {self.date_edit.date().toString('dd/MM/yyyy')}")
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        self.figure.tight_layout()
        self.canvas.draw()
        mn = float(self.prices.min())
        mx = float(self.prices.max())
        neg_count = int((self.prices < 0).sum())
        self.lbl_info.setText(f"Min : {mn:.2f} €/MWh   |   Max : {mx:.2f} €/MWh   |   Heures négatives : {neg_count}")

    def _verifier_seuil(self):
        if self.prices is None:
            QMessageBox.information(self, "Prix non chargés", "Chargez d'abord les prix avant de vérifier le seuil.")
            return
        threshold = self.spn_threshold.value()
        below = self.prices[self.prices < threshold]
        if below.empty:
            QMessageBox.information(self, "Aucune alerte", f"Aucun prix ne descend sous le seuil de {threshold:.2f} €/MWh pour cette journée.")
        else:
            lines = "\n".join(f"  {t.strftime('%H:%M')} : {v:.2f} €/MWh" for t, v in zip(below.index.to_pydatetime(), below.values))
            QMessageBox.warning(self, f"Alerte seuil — {threshold:.2f} €/MWh", f"Les prix descendent sous {threshold:.2f} €/MWh aux heures suivantes :\n\n{lines}")
            if self._get_manager_info:
                manager_name, manager_email = self._get_manager_info()
                if manager_email:
                    date_str = self.date_edit.date().toString("dd/MM/yyyy")
                    subject  = f"[Alerte prix] Seuil {threshold:.2f} €/MWh franchi — {date_str}"
                    body = (
                        f"Bonjour {manager_name},\n\n"
                        f"Une alerte de prix a été déclenchée pour le {date_str}.\n"
                        f"Le prix descend sous {threshold:.2f} €/MWh aux heures suivantes :\n\n"
                        f"{lines}\n\nVoodoo Production Manager"
                    )
                    self._alert_worker = SimpleEmailWorker(manager_email, subject, body)
                    self._alert_worker.start()

    def prix_actuels(self):
        return self.prices
