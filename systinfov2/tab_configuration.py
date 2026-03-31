import os

from PyQt6 import uic
from PyQt6.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QTableWidgetItem, QListWidgetItem,
    QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt

import database

_UI_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")
#Construit le chemin vers le dossier ui qui contient les fichiers Qt Designer. Par exemple : "C:/projet/systinfov2/ui".
#  Ce chemin est stocké dans _UI_DIR pour être réutilisé à plusieurs endroits.

class MachinesTab(QWidget):

    def __init__(self):
        super().__init__()
        self._id_selectionne = None #stocke l'id de la machine actuellement sélectionnée dans le tableau.
        uic.loadUi(os.path.join(_UI_DIR, "machines_tab.ui"), self)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.selectionModel().selectionChanged.connect(self._sur_selection)
        self.btn_add.clicked.connect(self._ajouter)
        self.btn_update.clicked.connect(self._modifier)
        self.btn_delete.clicked.connect(self._supprimer)
        self.btn_clear.clicked.connect(self._vider_formulaire)
        self.actualiser()

    def actualiser(self):
        self.table.setRowCount(0) #vide complètement le tableau. Sans ça, chaque rafraîchissement ajouterait des lignes en double
        for ligne_db in database.lister_machines():
            id_machine, nom, puissance, operateur, email, fixe = ligne_db
            ligne = self.table.rowCount()
            self.table.insertRow(ligne)
            self.table.setItem(ligne, 0, QTableWidgetItem(nom))
            self.table.setItem(ligne, 1, QTableWidgetItem(str(puissance)))
            self.table.setItem(ligne, 2, QTableWidgetItem(operateur or ""))
            self.table.setItem(ligne, 3, QTableWidgetItem(email or "")) #on affiche une chaîne vide plutôt que le mot "None
            self.table.setItem(ligne, 4, QTableWidgetItem(str(fixe)))
            self.table.item(ligne, 0).setData(Qt.ItemDataRole.UserRole, id_machine)
#On cache l'id de la machine dans la cellule du nom. L'utilisateur ne le voit pas, mais le code peut le récupérer plus tard. C'est comme écrire un numéro au dos d'une carte — visible si on retourne la carte, invisible sinon. On en aura besoin pour modifier ou supprimer la bonne machine.

    def _sur_selection(self): #selection tableau
        lignes_selectionnees = self.table.selectionModel().selectedRows() 
        if not lignes_selectionnees:
            return
        ligne = lignes_selectionnees[0].row()
        self._id_selectionne = self.table.item(ligne, 0).data(Qt.ItemDataRole.UserRole)#récupère l'id de la machine à partir de la cellule du nom, là où on l'avait caché
        self.inp_name.setText(self.table.item(ligne, 0).text())
        self.inp_power.setValue(float(self.table.item(ligne, 1).text()))
        self.inp_oper.setText(self.table.item(ligne, 2).text())
        self.inp_email.setText(self.table.item(ligne, 3).text())
        self.inp_fixed.setValue(float(self.table.item(ligne, 4).text())) #remplissage auto 

    def _ajouter(self):
        nom = self.inp_name.text().strip() #récupère le texte tapé dans le champ
        if not nom:
            QMessageBox.warning(self, "Champ manquant", "Le nom est obligatoire.")
            return
        database.ajouter_machine(nom, self.inp_power.value(), self.inp_oper.text().strip(), self.inp_email.text().strip(), self.inp_fixed.value())
        self._vider_formulaire()
        self.actualiser()

    def _modifier(self):
        if self._id_selectionne is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez d'abord une machine.")
            return
        nom = self.inp_name.text().strip()
        if not nom:
            QMessageBox.warning(self, "Champ manquant", "Le nom est obligatoire.")
            return
        database.modifier_machine(self._id_selectionne, nom, self.inp_power.value(), self.inp_oper.text().strip(), self.inp_email.text().strip(), self.inp_fixed.value())
        self._vider_formulaire()
        self.actualiser()

    def _supprimer(self):
        if self._id_selectionne is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez d'abord une machine.")
            return
        reponse = QMessageBox.question(self, "Confirmer", "Supprimer cette machine ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reponse == QMessageBox.StandardButton.Yes:
            database.supprimer_machine(self._id_selectionne) 
            self._vider_formulaire()
            self.actualiser()

#Supprime la machine de la base. Grâce au ON DELETE SET NULL dans database.py, 
#les étapes qui utilisaient cette machine ne sont pas supprimées — leur machine_id passe simplement à NULL

    def _vider_formulaire(self):
        self._id_selectionne = None
        self.inp_name.clear()
        self.inp_power.setValue(0)
        self.inp_oper.clear()
        self.inp_email.clear()
        self.inp_fixed.setValue(0)
        self.table.clearSelection()
#désélectionne la ligne dans le tableau — visuellement elle n'est plus surlignée


class ProductsTab(QWidget):

    def __init__(self):
        super().__init__()
        self._id_produit_courant = None
        uic.loadUi(os.path.join(_UI_DIR, "products_tab.ui"), self)
        self.table_tasks.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.list_products.currentItemChanged.connect(self._sur_selection_produit)
        self.btn_add_prod.clicked.connect(self._ajouter_produit)
        self.btn_ren_prod.clicked.connect(self._renommer_produit)
        self.btn_del_prod.clicked.connect(self._supprimer_produit)
        self.btn_add_step.clicked.connect(self._ajouter_etape)
        self.btn_del_step.clicked.connect(self._supprimer_etape)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.actualiser_produits()

#Un splitter est une barre séparatrice que l'utilisateur peut glisser pour redimensionner deux zones côte à côte
# setStretchFactor(0, 1) : la zone gauche (liste des produits) prend 1 part d'espace
# setStretchFactor(1, 2) : la zone droite (tableau des étapes) prend 2 parts d'espace — donc deux fois plus large que la liste

    def actualiser_produits(self):
        self.list_products.clear()
        for id_produit, nom_produit in database.lister_produits():
            element = QListWidgetItem(nom_produit)
            element.setData(Qt.ItemDataRole.UserRole, id_produit)
            self.list_products.addItem(element)

#Résultat visuel — une liste cliquable

    def _sur_selection_produit(self, element_courant, _precedent):
        if element_courant is None:
            self._id_produit_courant = None
            self.table_tasks.setRowCount(0)
            self.inp_prod_name.clear()
            return
        self._id_produit_courant = element_courant.data(Qt.ItemDataRole.UserRole)
        self.inp_prod_name.setText(element_courant.text())
        self._actualiser_etapes()

    def _ajouter_produit(self):
        nom = self.inp_prod_name.text().strip()
        if not nom:
            QMessageBox.warning(self, "Champ manquant", "Entrez un nom de produit.")
            return
        database.ajouter_produit(nom)
        self.inp_prod_name.clear()
        self.actualiser_produits()

    def _renommer_produit(self):
        if self._id_produit_courant is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez d'abord un produit à renommer.")
            return
        nom = self.inp_prod_name.text().strip()
        if not nom:
            QMessageBox.warning(self, "Champ manquant", "Entrez le nouveau nom du produit.")
            return
        database.modifier_produit(self._id_produit_courant, nom)
        self.actualiser_produits()

    def _supprimer_produit(self):
        element = self.list_products.currentItem()
        if element is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez un produit.")
            return
        reponse = QMessageBox.question(self, "Confirmer", f"Supprimer « {element.text()} » et toutes ses étapes ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reponse == QMessageBox.StandardButton.Yes:
            database.supprimer_produit(element.data(Qt.ItemDataRole.UserRole))
            self._id_produit_courant = None
            self.table_tasks.setRowCount(0)
            self.actualiser_produits()

    def _actualiser_etapes(self):
        self.table_tasks.setRowCount(0)
        if self._id_produit_courant is None:
            return
        for ligne_db in database.lister_etapes_produit(self._id_produit_courant):
            id_etape, ordre_etape, nom_machine, duree_min, _, puissance_w, *_ = ligne_db
            ligne = self.table_tasks.rowCount()
            self.table_tasks.insertRow(ligne)
            self.table_tasks.setItem(ligne, 0, QTableWidgetItem(str(ordre_etape)))
            self.table_tasks.setItem(ligne, 1, QTableWidgetItem(nom_machine))
            self.table_tasks.setItem(ligne, 2, QTableWidgetItem(str(duree_min)))
            self.table_tasks.setItem(ligne, 3, QTableWidgetItem(str(puissance_w)))
            self.table_tasks.item(ligne, 0).setData(Qt.ItemDataRole.UserRole, id_etape)

    def actualiser_combo_machines(self):
        self.cmb_machine.clear()
        for id_machine, nom_machine, *_ in database.lister_machines():
            self.cmb_machine.addItem(nom_machine, id_machine)

    def _ajouter_etape(self):
        if self._id_produit_courant is None:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez d'abord un produit.")
            return
        id_machine  = self.cmb_machine.currentData() #récupère l'id caché de la machine sélectionnée dans la liste déroulante
        duree       = self.spn_duration.value()
        ordre_etape = database.prochain_ordre_etape(self._id_produit_courant)
        database.ajouter_etape(self._id_produit_courant, id_machine, duree, ordre_etape)
        self._actualiser_etapes()

    def _supprimer_etape(self):
        lignes_selectionnees = self.table_tasks.selectionModel().selectedRows()
        if not lignes_selectionnees:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez une étape à supprimer.")
            return
        id_etape = self.table_tasks.item(lignes_selectionnees[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        database.supprimer_etape(id_etape)
        self._actualiser_etapes()


class ConfigTab(QWidget): # Onglet de configuration principal — contient les sous-onglets Machines et Produits

    def __init__(self):
        super().__init__()
        disposition    = QVBoxLayout(self)
        sous_onglets   = QTabWidget()
        self.onglet_machines = MachinesTab()
        self.onglet_produits = ProductsTab()
        sous_onglets.addTab(self.onglet_machines, "Machines")
        sous_onglets.addTab(self.onglet_produits, "Produits")
        sous_onglets.currentChanged.connect(self._changement_sous_onglet)
        disposition.addWidget(sous_onglets)
        self._sous_onglets = sous_onglets

    def _changement_sous_onglet(self, indice): # Actualise les données quand l'utilisateur change de sous-onglet
        if indice == 1:
            self.onglet_produits.actualiser_combo_machines()
            self.onglet_produits.actualiser_produits()
        if indice == 0:
            self.onglet_machines.actualiser()
