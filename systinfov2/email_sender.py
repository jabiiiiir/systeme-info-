# ==============================================================================
# email_sender.py - Envoi automatique d'emails aux opérateurs
#
# Utilise le protocole SMTP avec TLS (compatible Gmail).
# Pour Gmail : activez la validation en 2 étapes, puis créez un
# "Mot de passe d'application" dans les paramètres de votre compte Google.
# ==============================================================================

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# MIMEMultipart : crée la structure générale du message — c'est comme l'enveloppe qui contiendra tout
# MIMEText : représente le contenu texte du message — c'est la lettre à l'intérieur de l'enveloppe

import config

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT   = 587

# SMTP_SERVER : l'adresse du serveur d'envoi de Gmail
# SMTP_PORT : le numéro de port utilisé pour la connexion. Le port 587 est le standard pour les connexions sécurisées avec TLS

def envoyer_email(to_email, subject, body):
    """
    Envoie un email en texte brut.

    Paramètres :
        to_email : adresse email du destinataire
        subject  : objet du message
        body     : corps du message

    Retourne True si l'envoi réussit, False sinon.
    """
    msg = MIMEMultipart()
    msg["From"]    = config.EMAIL_SENDER
    msg["To"]      = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

# "plain" signifie que c'est du texte brut — pas de HTML, pas de mise en forme
# "utf-8" est l'encodage utilisé, ce qui permet d'écrire des caractères spéciaux comme les accents français

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()                          # Chiffrement TLS
            server.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[Email] Erreur envoi vers {to_email} : {e}")
        return False


def construire_planning_operateur(operator_name, schedule_lines):
    """
    Construit le corps de l'email de planning destiné à un opérateur.

    Paramètres :
        operator_name  : prénom/nom de l'opérateur
        schedule_lines : liste de chaînes décrivant chaque tâche

    Retourne une chaîne (le corps de l'email).
    """
    body  = f"Bonjour {operator_name},\n\n"
    body += "Voici votre planning de production pour aujourd'hui :\n\n"
    for line in schedule_lines:
        body += f"  - {line}\n"
    body += "\nBonne journée de travail,\nVoodoo Production Manager"
    return body
