

import smtplib#envoyer mail
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# MIMEMultipart : crée la structure générale du message 
# MIMEText : représente le contenu texte du message 

import config

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT   = 587

# SMTP_SERVER : l'adresse du serveur d'envoi de Gmail
# SMTP_PORT : le numéro de port utilisé pour la connexion. Le port 587 est le standard pour les connexions sécurisées avec TLS

def envoyer_email(email_destinataire, sujet, corps):

    message = MIMEMultipart()
    message["From"]    = config.EMAIL_SENDER
    message["To"]      = email_destinataire
    message["Subject"] = sujet
    message.attach(MIMEText(corps, "plain", "utf-8"))

# "plain" signifie que c'est du texte brut — pas de HTML, pas de mise en forme
# "utf-8" est l'encodage utilisé, ce qui permet d'écrire des caractères spéciaux comme les accents français

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as serveur:
            serveur.ehlo() # C'est une étape obligatoire du protocole
            serveur.starttls() # protection TLS : la connexion est chiffrée
            serveur.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            serveur.send_message(message)
        return True
    except Exception as erreur:
        print(f"[Email] Erreur envoi vers {email_destinataire} : {erreur}")
        return False


def construire_planning_operateur(nom_operateur, lignes_planning): #corps email

    corps  = f"Bonjour {nom_operateur},\n\n"
    corps += "Voici votre planning de production pour aujourd'hui :\n\n"
    for ligne in lignes_planning:
        corps += f"  - {ligne}\n"
    corps += "\nBonne journée de travail,\nVoodoo Production Manager"
    return corps
