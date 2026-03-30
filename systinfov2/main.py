import sys
# sys.argv : transmet les arguments de la ligne de commande à l'application
# sys.exit() : ferme proprement l'application quand l'utilisateur ferme la fenêtre
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit
)

import database
from tab_prix          import PricesTab
from tab_configuration import ConfigTab
from tab_commandes     import OrdersTab


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__() # sans ça la fenêtre ne fonctionnerait pas correctement car elle ne serait pas correctement initialisée par PyQt6
        self.setWindowTitle("Boulangerie Jaber-Hajji")
        self.resize(1100, 700)

        database.creer_tables()
        self._charger_demo()

        # Barre d'identification
        boite_id = QGroupBox("Identification")
        formulaire_id = QHBoxLayout(boite_id)
        formulaire_id.addWidget(QLabel("Nom / Entreprise :"))
        self.champ_nom = QLineEdit()
        formulaire_id.addWidget(self.champ_nom)
        formulaire_id.addWidget(QLabel("Email :"))
        self.champ_email = QLineEdit()
        formulaire_id.addWidget(self.champ_email)

        # Onglets
        onglets = QTabWidget()
        self.onglet_prix          = PricesTab(get_manager_info=self._infos_responsable)
        self.onglet_configuration = ConfigTab()
        self.onglet_commandes     = OrdersTab(self.onglet_prix, get_manager_info=self._infos_responsable) #accès direct aux champs nom/email de la barre d'identification
        onglets.addTab(self.onglet_configuration, "Configuration") #On ajoute les onglets dans l'ordre d'affichage
        onglets.addTab(self.onglet_prix,          "Prix Électricité")
        onglets.addTab(self.onglet_commandes,     "Commandes")
        onglets.currentChanged.connect(self._changement_onglet) #PyQt6 émet un signal avec le numéro du nouvel onglet

        widget_central = QWidget()
        disposition    = QVBoxLayout(widget_central)
        disposition.setContentsMargins(6, 6, 6, 6)
        disposition.setSpacing(4)
        disposition.addWidget(boite_id)
        disposition.addWidget(onglets)
        self.setCentralWidget(widget_central)
        self._onglets = onglets

        self._appliquer_style()

    def _infos_responsable(self):
        return (
            self.champ_nom.text().strip(),
            self.champ_email.text().strip(),
        )

    def _changement_onglet(self, indice):
        if indice == 2:
            self.onglet_commandes.actualiser_combo_produits()
            self.onglet_commandes._actualiser_commandes()

    def _charger_demo(self):
        if database.lister_machines():
            return
        machines = [
            ("Pétrin industriel",       3000,  "Ahmed Benali",  "ahmed.benali@voodoo.be",  5.0),
            ("Four tunnel",             1500, "Sophie Dupont", "sophie.dupont@voodoo.be", 20.0),
            ("Chambre de fermentation", 500,   "Ahmed Benali",  "ahmed.benali@voodoo.be",  2.0),
            ("Trancheuse-emballeuse",   800,   "Marc Lecomte",  "marc.lecomte@voodoo.be",  3.0),
        ]
        identifiants = {}
        for nom, puissance, operateur, email, fixe in machines:
            identifiants[nom] = database.ajouter_machine(nom, puissance, operateur, email, fixe)

        taches_produits = {
            "Pain blanc":       [(identifiants["Pétrin industriel"], 20), (identifiants["Chambre de fermentation"], 60), (identifiants["Four tunnel"], 30), (identifiants["Trancheuse-emballeuse"], 10)],
            "Baguette":         [(identifiants["Pétrin industriel"], 15), (identifiants["Chambre de fermentation"], 45), (identifiants["Four tunnel"], 25)],
            "Croissants":       [(identifiants["Pétrin industriel"], 30), (identifiants["Chambre de fermentation"], 90), (identifiants["Four tunnel"], 20), (identifiants["Trancheuse-emballeuse"], 5)],
            "Pain de campagne": [(identifiants["Pétrin industriel"], 25), (identifiants["Chambre de fermentation"], 75), (identifiants["Four tunnel"], 40)],
        }
        for nom_produit, etapes in taches_produits.items():
            id_produit = database.ajouter_produit(nom_produit)
            for ordre, (id_machine, duree) in enumerate(etapes, start=1):
                database.ajouter_etape(id_produit, id_machine, duree, ordre)

    def _appliquer_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #fdf6ec;
                color: #3b2a1a;
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
            QTabWidget::pane { border: 1px solid #d4a96a; border-radius: 4px; }
            QTabBar::tab { background: #e8c99a; padding: 6px 16px; border: 1px solid #d4a96a; border-bottom: none; border-radius: 4px 4px 0 0; }
            QTabBar::tab:selected { background: #fdf6ec; font-weight: bold; }
            QPushButton { background-color: #c0722a; color: white; border: none; padding: 6px 14px; border-radius: 4px; }
            QPushButton:hover { background-color: #a85c20; }
            QTableWidget { background-color: white; gridline-color: #e8c99a; }
            QHeaderView::section { background-color: #e8c99a; padding: 4px; border: 1px solid #d4a96a; }
            QGroupBox { border: 1px solid #d4a96a; border-radius: 4px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; font-weight: bold; color: #7a4010; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit { background-color: white; border: 1x solid #d4a96a; border-radius: 3px; padding: 3px 6px; }
            QListWidget { background-color: white; border: 1px solid #d4a96a; }
        """)


if __name__ == "__main__":
    application = QApplication(sys.argv)
    fenetre = MainWindow()
    fenetre.show()
    sys.exit(application.exec())
#push
#test
