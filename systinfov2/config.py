# ==============================================================================
# config.py - Fichier de configuration des identifiants
# Modifiez uniquement ce fichier pour adapter l'application à vos accès.
# ==============================================================================

# Token ENTSO-E (https://transparency.entsoe.eu/)
ENTSOE_TOKEN = "cbe182ef-2b82-499b-b771-0d933d3b5a57"

# Paramètres email (expéditeur des notifications aux opérateurs)
# Pour Gmail : activez la validation en 2 étapes puis créez un "Mot de passe d'application"
# dans les paramètres de votre compte Google.
EMAIL_SENDER   = "jaberhajji2005@gmail.com"
EMAIL_PASSWORD = "ekfaxwefhwfojebx" #ekfaxwefhwfojebx
#Le compte Gmail qui envoie les emails automatiques.
#  Le mot de passe ici n'est pas le vrai mot de passe Gmail, c'est un "mot de passe d'application" — un code spécial généré par Google pour les apps tierces (plus sécurisé).

# Zone géographique ENTSO-E (BE = Belgique)
COUNTRY_CODE = "BE"
#Ce fichier est intentionnellement séparé du reste du code : si tu changes de compte email ou de token, tu modifies uniquement ce fichier, sans toucher à la logique.