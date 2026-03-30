import os
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QMessageBox
from PyQt6.QtCore import QDate, QThread, QTimer, pyqtSignal

import matplotlib #librairie pour graph
matplotlib.use("QtAgg")#utilise PyQt6 pour afficher tes graphiques
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

import database
import api_entsoe
import email_sender

_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
#Si tu lances le programme depuis un autre dossier (ex: python systinfov2/main.py depuis le bureau), 
# le chemin relatif "ui" serait calculé depuis le bureau — et Python ne trouverait pas les fichiers.
#  En ancrant le chemin à __file__, le dossier ui/ est toujours trouvé peu importe d'où le programme est lancé.

class PriceWorker(QThread):  #on envoie un "assistant" télécharger les prix
    finished = pyqtSignal(object)
    error    = pyqtSignal(str)

    def __init__(self, date):
        super().__init__()
        self.date = date

    def run(self):
        try:
            self.finished.emit(api_entsoe.recuperer_prix_journaliers(self.date))
        except Exception as erreur:
            self.error.emit(str(erreur))
#je donne la date à ce worker, il va faire le travail de récupérer les prix (potentiellement long) dans un thread séparé pour ne pas bloquer l'interface.
#Quand il a fini, il émet un signal "finished" avec les prix récupérés, ou un signal "error" avec le message d'erreur s'il y a un problème.

class SimpleEmailWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, email_destinataire, sujet, corps):
        super().__init__()
        self.email_destinataire = email_destinataire
        self.sujet              = sujet
        self.corps              = corps

    def run(self):
        try:
            ok = email_sender.envoyer_email(self.email_destinataire, self.sujet, self.corps)
            self.finished.emit(ok, "" if ok else "Échec inconnu")
        except Exception as erreur:
            self.finished.emit(False, str(erreur))

#Ce worker est utilisé pour envoyer un email d'alerte si le seuil de prix est franchi. Comme l'envoi d'email peut aussi prendre du temps, on le fait dans un thread séparé pour ne pas bloquer l'interface. Quand il a fini, il émet un signal "finished" avec un booléen indiquant si l'envoi a réussi, et un message d'erreur s'il y en a une 

class PricesTab(QWidget):

    def __init__(self, get_manager_info=None):
        super().__init__()
        self.prix              = None
        self._get_manager_info = get_manager_info
        uic.loadUi(os.path.join(_UI_DIR, "prices_tab.ui"), self) #charge depuis qt designer
        self.date_edit.setDate(QDate.currentDate())
        self.graphique = Figure(figsize=(8, 4))
        self.canevas   = FigureCanvas(self.graphique) #canvas = zone de dessin pour matplotlib
        self.canvas_container.layout().addWidget(self.canevas)
        self.btn_load.clicked.connect(self.charger_prix)
        self.btn_check_threshold.clicked.connect(self._verifier_seuil)
        QTimer.singleShot(100, self._chargement_auto_prix) #marge de temps

    def _chargement_auto_prix(self):
        chaine_date = self.date_edit.date().toString("yyyy-MM-dd")
        en_cache    = database.charger_prix_electricite(chaine_date)
        if en_cache is not None:
            self.prix = en_cache
            self.lbl_info.setText("Prix chargés depuis le cache local.")
            self._dessiner_graphique()
        else:
            self.charger_prix()

    def charger_prix(self):
        date_qt    = self.date_edit.date()
        date_cible = datetime(date_qt.year(), date_qt.month(), date_qt.day())
        self.btn_load.setEnabled(False) # désactive le bouton pendant le chargement
        self.lbl_info.setText("Chargement en cours…")
        self._worker = PriceWorker(date_cible)
        self._worker.finished.connect(self._prix_charges)
        self._worker.error.connect(self._erreur_chargement)
        self._worker.start()

    def _prix_charges(self, prix):
        self.prix   = prix
        chaine_date = self.date_edit.date().toString("yyyy-MM-dd")
        database.sauvegarder_prix_electricite(chaine_date, prix)
        self.btn_load.setEnabled(True)
        self._dessiner_graphique()
        self._verifier_seuil()

    def _erreur_chargement(self, message):
        self.btn_load.setEnabled(True)
        self.lbl_info.setText("Échec du chargement.")
        QMessageBox.critical(self, "Erreur API", f"Impossible de récupérer les prix :\n{message}")

#je peux effacer?
    def _dessiner_graphique(self):
        self.graphique.clear()
        ax       = self.graphique.add_subplot(111)
        instants = self.prix.index.to_pydatetime()
        valeurs  = self.prix.values
        couleurs = ["#e74c3c" if v < 0 else "#2ecc71" for v in valeurs]
        ax.bar(range(len(valeurs)), valeurs, color=couleurs, width=0.8)
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        pas = max(1, len(instants) // 12)
        ax.set_xticks(range(0, len(instants), pas))
        ax.set_xticklabels([t.strftime("%H:%M") for t in instants[::pas]], rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("EUR / MWh")
        ax.set_title(f"Prix day-ahead — {self.date_edit.date().toString('dd/MM/yyyy')}")
        ax.grid(axis="y", linestyle=":", alpha=0.5)
        self.graphique.tight_layout()
        self.canevas.draw() #graph 
        minimum     = float(self.prix.min())
        maximum     = float(self.prix.max()) 
        nb_negatifs = int((self.prix < 0).sum())
        self.lbl_info.setText(f"Min : {minimum:.2f} €/MWh   |   Max : {maximum:.2f} €/MWh   |   Heures négatives : {nb_negatifs}")


    def _verifier_seuil(self):
        if self.prix is None:
            QMessageBox.information(self, "Prix non chargés", "Chargez d'abord les prix avant de vérifier le seuil.")
            return
        seuil      = self.spn_threshold.value()
        en_dessous = self.prix[self.prix < seuil]
        if en_dessous.empty:
            QMessageBox.information(self, "Aucune alerte", f"Aucun prix ne descend sous le seuil de {seuil:.2f} €/MWh pour cette journée.")
        else:
            lignes = "\n".join(f"  {t.strftime('%H:%M')} : {v:.2f} €/MWh" for t, v in zip(en_dessous.index.to_pydatetime(), en_dessous.values))
            QMessageBox.warning(self, f"Alerte seuil — {seuil:.2f} €/MWh", f"Les prix descendent sous {seuil:.2f} €/MWh aux heures suivantes :\n\n{lignes}")
            if self._get_manager_info:
                nom_responsable, email_responsable = self._get_manager_info()
                if email_responsable:
                    chaine_date = self.date_edit.date().toString("dd/MM/yyyy")
                    sujet = f"[Alerte prix] Seuil {seuil:.2f} €/MWh franchi — {chaine_date}"
                    corps = (
                        f"Bonjour {nom_responsable},\n\n"
                        f"Une alerte de prix a été déclenchée pour le {chaine_date}.\n"
                        f"Le prix descend sous {seuil:.2f} €/MWh aux heures suivantes :\n\n"
                        f"{lignes}\n\nVoodoo Production Manager"
                    )
                    self._worker_alerte = SimpleEmailWorker(email_responsable, sujet, corps)
                    self._worker_alerte.start()

    def prix_actuels(self):
        return self.prix
#Elle est appelée par tab_commandes.py pour calculer les coûts des commandes.