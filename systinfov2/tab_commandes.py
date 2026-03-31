import os # Pour construire les chemins vers les fichiers UI
import importlib# Pour recharger la configuration des emails à chaque envoi
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PyQt6 import uic
from PyQt6.QtWidgets import QWidget, QTableWidgetItem, QMessageBox, QHeaderView
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal

import database
import api_entsoe
import email_sender

_FUSEAU_HORAIRE = ZoneInfo("Europe/Brussels")
_UI_DIR         = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui")  
#Qt Designer. __file__ est le chemin du fichier actuel, os.path.dirname prend son dossier parent, et on y ajoute "ui"


class EmailWorker(QThread): #on utilise un thread séparé pour envoyer les emails sans bloquer l'interface.
    
    finished = pyqtSignal(int, list)

    def __init__(self, plannings, date_commande): #plannings est un dict avec comme clé un tuple (nom_operateur, email_operateur) 
        super().__init__()
        self.plannings      = plannings
        self.date_commande  = date_commande

    def run(self):# Cette méthode est exécutée dans le thread séparé quand on appelle start() sur le worker. 
        envoyes, erreurs = 0, []
        for (nom_operateur, email_operateur), lignes in self.plannings.items():
            if not email_operateur:
                continue
            sujet = f"Planning de production du {self.date_commande}"
            corps = email_sender.construire_planning_operateur(nom_operateur, lignes)
            try:
                if email_sender.envoyer_email(email_operateur, sujet, corps):
                    envoyes += 1
                else:
                    erreurs.append(f"{nom_operateur} <{email_operateur}> : échec inconnu")
            except Exception as erreur:
                erreurs.append(f"{nom_operateur} <{email_operateur}> : {erreur}")
        self.finished.emit(envoyes, erreurs)


class SimpleEmailWorker(QThread): # Envoie un email à un seul destinataire dans un thread séparé pour ne pas bloquer l'interface
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


class OrdersTab(QWidget): # Onglet de gestion des commandes journalières — ajout, suppression, calcul des coûts et envoi des plannings

    def __init__(self, prices_tab, get_manager_info=None):
        super().__init__()
        self._onglet_prix          = prices_tab
        self._get_manager_info     = get_manager_info
        uic.loadUi(os.path.join(_UI_DIR, "orders_tab.ui"), self)
        self.date_order.setDate(QDate.currentDate())
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        police = self.lbl_total.font()
        self.btn_add_order.clicked.connect(self._ajouter_commande)
        self.btn_delete.clicked.connect(self._supprimer_commande)
        self.btn_calc.clicked.connect(self._calculer_couts)
        self.btn_email.clicked.connect(self._envoyer_emails)
        self.btn_refresh.clicked.connect(self._actualiser_commandes)
        self._actualiser_commandes()


    def actualiser_combo_produits(self):
        self.cmb_product.clear()
        for id_produit, nom_produit in database.lister_produits():
            self.cmb_product.addItem(nom_produit, id_produit)

#Vide la liste déroulante des produits puis la remplit

    def _actualiser_commandes(self): # Recharge le tableau avec les commandes enregistrées pour la date sélectionnée
        self.table.setRowCount(0)
        date_commande = self.date_order.date().toString("yyyy-MM-dd")
        for ligne_db in database.lister_commandes_du_jour(date_commande):
            id_commande, nom_produit, heure_debut, id_produit = ligne_db
            ligne = self.table.rowCount()#le numéro de la ligne à insérer est égal au nombre de lignes déjà présentes
            self.table.insertRow(ligne)
            self.table.setItem(ligne, 0, QTableWidgetItem(nom_produit))
            self.table.setItem(ligne, 1, QTableWidgetItem(heure_debut))
            self.table.setItem(ligne, 2, QTableWidgetItem("—")) # pas encore calculée donc "—"
            self.table.setItem(ligne, 3, QTableWidgetItem("—"))
            self.table.setItem(ligne, 4, QTableWidgetItem(date_commande))
            self.table.item(ligne, 0).setData(Qt.ItemDataRole.UserRole, id_commande)#On cache l'id_produit dans la colonne 1
            self.table.item(ligne, 1).setData(Qt.ItemDataRole.UserRole, id_produit)
        self.lbl_total.setText("")

    def _ajouter_commande(self):
        if self.cmb_product.count() == 0:
            QMessageBox.warning(self, "Aucun produit", "Ajoutez d'abord des produits dans la configuration.")
            return
        id_produit    = self.cmb_product.currentData()
        heure_debut   = self.time_start.time().toString("HH:mm")
        date_commande = self.date_order.date().toString("yyyy-MM-dd")
        etapes        = database.lister_etapes_produit(id_produit)
        total_minutes = sum(etape[3] for etape in etapes)
        dt_debut      = datetime.strptime(f"{date_commande} {heure_debut}", "%Y-%m-%d %H:%M")
        dt_fin        = dt_debut + timedelta(minutes=total_minutes)
    #calcul du temps de la commande 

        if dt_fin.date() > dt_debut.date():
            QMessageBox.warning(self, "Dépassement de minuit", f"Ce produit dure {total_minutes} min et dépasse minuit.\nChoisissez une heure de début plus tôt.")
            return

        database.ajouter_commande(id_produit, heure_debut, date_commande)
        self._actualiser_commandes()

        if self._get_manager_info:
            nom_responsable, email_responsable = self._get_manager_info()
            if email_responsable:
                nom_produit = self.cmb_product.currentText()
                sujet = f"[Commande] {nom_produit} — {date_commande}"
                corps = (
                    f"Bonjour {nom_responsable},\n\n"
                    f"Une nouvelle commande a été enregistrée :\n\n"
                    f"  Produit    : {nom_produit}\n"
                    f"  Date       : {date_commande}\n"
                    f"  Heure début: {heure_debut}\n"
                    f"  Durée tot. : {total_minutes} min\n"
                    f"  Fin prévue : {dt_fin.strftime('%H:%M')}\n\nVoodoo Production Manager"
                )
                self._worker_commande = SimpleEmailWorker(email_responsable, sujet, corps)
                self._worker_commande.start()

    def _supprimer_commande(self): # Supprime la commande sélectionnée dans le tableau et actualise l'affichage
        lignes_selectionnees = self.table.selectionModel().selectedRows()
        if not lignes_selectionnees:
            QMessageBox.warning(self, "Sélection requise", "Sélectionnez une commande.")
            return
        id_commande = self.table.item(lignes_selectionnees[0].row(), 0).data(Qt.ItemDataRole.UserRole) #récupère l'id caché de la commande dans la cellule colonne 0
        database.supprimer_commande(id_commande)
        self._actualiser_commandes()

    def _calculer_couts(self): # Calcule le coût énergétique et fixe de chaque commande selon les prix ENTSO-E et affiche le total
        prix          = self._onglet_prix.prix_actuels()
        date_commande = self.date_order.date().toString("yyyy-MM-dd")
        cout_total    = 0.0

        for ligne in range(self.table.rowCount()): 
            id_commande = self.table.item(ligne, 0).data(Qt.ItemDataRole.UserRole)
            id_produit  = self.table.item(ligne, 1).data(Qt.ItemDataRole.UserRole)
            heure_debut = self.table.item(ligne, 1).text()
            dt_courant  = datetime.strptime(f"{date_commande} {heure_debut}", "%Y-%m-%d %H:%M")
            etapes      = database.lister_etapes_produit(id_produit)
            cout_commande = 0.0

            for etape in etapes:
                _, _, _, duree_min, _, puissance_w, _, _, cout_fixe = etape
                energie_mwh    = (puissance_w / 1_000_000) * (duree_min / 60)
                prix_instant   = api_entsoe.obtenir_prix_a_instant(prix, dt_courant) if prix is not None else 0.0
                cout_commande += energie_mwh * prix_instant + cout_fixe
                dt_courant    += timedelta(minutes=duree_min)

            dt_debut      = datetime.strptime(f"{date_commande} {heure_debut}", "%Y-%m-%d %H:%M")
            total_min     = sum(etape[3] for etape in etapes)
            heure_fin     = (dt_debut + timedelta(minutes=total_min)).strftime("%H:%M")
            self.table.setItem(ligne, 2, QTableWidgetItem(heure_fin))
            self.table.setItem(ligne, 3, QTableWidgetItem(f"{cout_commande:.2f} €"))
            cout_total += cout_commande

            # Sauvegarde l'id du prix d'électricité utilisé pour cette commande
            if prix is not None:
                horodatage_debut = dt_debut.replace(tzinfo=_FUSEAU_HORAIRE) #sans fuseau horaire, la comparaison hour_ts <= ? ne fonctionnerait pas correctement.
                prix_id = database.trouver_id_prix_electricite(
                    date_commande,
                    horodatage_debut.isoformat()
                )
                database.modifier_commande(id_commande, prix_id)

#La base de données sait maintenant quel prix d'électricité correspond à chaque commande

        self.lbl_total.setText(f"Coût total estimé : {cout_total:.2f} €")

        if prix is None:
            QMessageBox.information(self, "Prix non chargés", "Les prix d'électricité n'ont pas été chargés.\nLes coûts énergétiques sont calculés à 0 €/MWh.\nChargez les prix dans l'onglet « Prix Électricité ».")

    def _envoyer_emails(self): # Construit les plannings par opérateur et les envoie par email via un worker en arrière-plan
        date_commande = self.date_order.date().toString("yyyy-MM-dd")
        commandes = database.lister_commandes_du_jour(date_commande)
        if not commandes:
            QMessageBox.information(self, "Aucune commande", "Aucune commande à envoyer.")
            return

        plannings: dict = {}
        for _, nom_produit, heure_debut, id_produit in commandes:
            dt_courant = datetime.strptime(f"{date_commande} {heure_debut}", "%Y-%m-%d %H:%M").replace(tzinfo=_FUSEAU_HORAIRE)
            for etape in database.lister_etapes_produit(id_produit):
                _, ordre_etape, nom_machine, duree_min, _, _, nom_operateur, email_operateur, _ = etape
                cle    = (nom_operateur or "", email_operateur or "")
                dt_fin = dt_courant + timedelta(minutes=duree_min)
                ligne  = f"{nom_produit} — Étape {ordre_etape} ({nom_machine}) : {dt_courant.strftime('%H:%M %Z')} → {dt_fin.strftime('%H:%M %Z')} ({duree_min} min)"
                plannings.setdefault(cle, []).append(ligne)
                dt_courant = dt_fin

        if not plannings:
            QMessageBox.information(self, "Aucun opérateur", "Aucun opérateur n'est associé aux tâches de ces commandes.")
            return

        import config as _configuration
        importlib.reload(_configuration)
        if _configuration.EMAIL_SENDER == "votre.email@gmail.com" or _configuration.EMAIL_PASSWORD == "votre_app_password":
            QMessageBox.warning(self, "Email non configuré", "Les identifiants email sont encore des valeurs par défaut dans config.py.")
            return

        email_supplementaire = self.inp_extra_email.text().strip()
        if email_supplementaire:
            toutes_lignes = []
            for (nom_operateur, _), lignes in plannings.items():
                toutes_lignes.append(f"[ {nom_operateur} ]")
                toutes_lignes.extend(lignes)
                toutes_lignes.append("")
            plannings[("Planning complet", email_supplementaire)] = toutes_lignes

        self.btn_email.setEnabled(False)
        self.btn_email.setText("Envoi en cours…")
        self._worker_email = EmailWorker(plannings, date_commande)
        self._worker_email.finished.connect(self._emails_envoyes)
        self._worker_email.start()

    def _emails_envoyes(self, envoyes, erreurs): # Callback appelé quand le worker email a terminé — réactive le bouton et affiche le résultat
        self.btn_email.setEnabled(True)
        self.btn_email.setText("Envoyer les plannings par email")
        message = f"Emails envoyés avec succès : {envoyes}"
        if erreurs:
            message += "\n\nÉchecs :\n" + "\n".join(erreurs)
        QMessageBox.information(self, "Résultat envoi", message)
