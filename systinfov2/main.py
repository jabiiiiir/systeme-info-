import sys
# sys.argv : transmet les arguments de la ligne de commande à l'application
# sys.exit() : ferme proprement l'application quand l'utilisateur ferme la fenêtre
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox, QLabel, QLineEdit
)

import database as db
from tab_prix          import PricesTab
from tab_configuration import ConfigTab
from tab_commandes     import OrdersTab


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__() # sans ça la fenêtre ne fonctionnerait pas correctement car elle ne serait pas correctement initialisée par PyQt6
        self.setWindowTitle("Boulangerie Jaber-Hajji")
        self.resize(1100, 700)

        db.creer_tables()
        self._charger_demo()

        # Barre d'identification
        id_box = QGroupBox("Identification")
        id_form = QHBoxLayout(id_box)
        id_form.addWidget(QLabel("Nom / Entreprise :"))
        self.inp_manager_name = QLineEdit()
        id_form.addWidget(self.inp_manager_name)
        id_form.addWidget(QLabel("Email :"))
        self.inp_manager_email = QLineEdit()
        id_form.addWidget(self.inp_manager_email)

        # Onglets
        tabs = QTabWidget()
        self.prices_tab = PricesTab(get_manager_info=self._infos_responsable)
        self.config_tab = ConfigTab()
        self.orders_tab = OrdersTab(self.prices_tab, get_manager_info=self._infos_responsable) #accès direct aux champs nom/email de la barre d'identification
        tabs.addTab(self.config_tab,  "Configuration") #On ajoute les onglets dans l'ordre d'affichage
        tabs.addTab(self.prices_tab,  "Prix Électricité")
        tabs.addTab(self.orders_tab,  "Commandes")
        tabs.currentChanged.connect(self._changement_onglet) #PyQt6 émet un signal avec le numéro du nouvel onglet

        central = QWidget()
        layout  = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.addWidget(id_box)
        layout.addWidget(tabs)
        self.setCentralWidget(central)
        self._tabs = tabs

        self._appliquer_style()

    def _infos_responsable(self):
        return (
            self.inp_manager_name.text().strip(),
            self.inp_manager_email.text().strip(),
        )

    def _changement_onglet(self, index):
        if index == 2:
            self.orders_tab.actualiser_combo_produits()
            self.orders_tab._actualiser_commandes()

    def _charger_demo(self):
        if db.lister_machines():
            return
        machines = [
            ("Pétrin industriel",       3000,  "Ahmed Benali",  "ahmed.benali@voodoo.be",  5.0),
            ("Four tunnel",             1500, "Sophie Dupont", "sophie.dupont@voodoo.be", 20.0),
            ("Chambre de fermentation", 500,   "Ahmed Benali",  "ahmed.benali@voodoo.be",  2.0),
            ("Trancheuse-emballeuse",   800,   "Marc Lecomte",  "marc.lecomte@voodoo.be",  3.0),
        ]
        ids = {}
        for name, power, oper, email, fixed in machines:
            ids[name] = db.ajouter_machine(name, power, oper, email, fixed )

        products_tasks = {
            "Pain blanc":       [(ids["Pétrin industriel"], 20), (ids["Chambre de fermentation"], 60), (ids["Four tunnel"], 30), (ids["Trancheuse-emballeuse"], 10)],
            "Baguette":         [(ids["Pétrin industriel"], 15), (ids["Chambre de fermentation"], 45), (ids["Four tunnel"], 25)],
            "Croissants":       [(ids["Pétrin industriel"], 30), (ids["Chambre de fermentation"], 90), (ids["Four tunnel"], 20), (ids["Trancheuse-emballeuse"], 5)],
            "Pain de campagne": [(ids["Pétrin industriel"], 25), (ids["Chambre de fermentation"], 75), (ids["Four tunnel"], 40)],
        }
        for prod_name, steps in products_tasks.items():
            p_id = db.ajouter_produit(prod_name)
            for order, (machine_id, duration) in enumerate(steps, start=1):
                db.ajouter_etape(p_id, machine_id, duration, order)

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
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
#push
#test