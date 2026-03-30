# ==============================================================================
# api_entsoe.py - Récupération des prix d'électricité via l'API ENTSO-E
#
# Utilise la librairie entsoe-py (pip install entsoe-py)
# Documentation : https://github.com/EnergieID/entsoe-py
# ==============================================================================

import pandas
#: une librairie pour manipuler des tableaux de données. Ici on l'utilise pour stocker les prix sous forme de série temporelle (une valeur par heure).
from datetime import datetime

try:
    from entsoe import EntsoePandasClient
    ENTSOE_DISPONIBLE = True
except ImportError:
    ENTSOE_DISPONIBLE = False
#Cela permet à l'application de démarrer quand même et d'afficher un message d'erreur clair plus tard.

import config


def recuperer_prix_journaliers(date=None):
    """
    Récupère les prix day-ahead du marché belge pour une date donnée.

    Paramètres :
        date : datetime ou None (None = aujourd'hui)

    Retourne :
        pandas.Series avec les prix en EUR/MWh, indexé par timestamp (Europe/Brussels)

    Lève une exception si l'API est indisponible ou le token invalide.
    """
    if not ENTSOE_DISPONIBLE:
        raise ImportError(
            "La librairie entsoe-py n'est pas installée.\n"
            "Exécutez : pip install entsoe-py"
        )

    service = EntsoePandasClient(api_key=config.ENTSOE_TOKEN)

    if date is None:
        date = datetime.now()

    # Début et fin de la journée en heure locale belge
    debut = pandas.Timestamp(date.strftime("%Y%m%d"), tz="Europe/Brussels")
    fin   = debut + pandas.Timedelta(days=1)

    prix = service.query_day_ahead_prices(config.COUNTRY_CODE, start=debut, end=fin)
    return prix


def obtenir_prix_a_instant(prix, dt):
    """
    Retourne le prix de l'électricité (EUR/MWh) à un instant donné.

    Paramètres :
        prix : pandas.Series retourné par recuperer_prix_journaliers()
        dt   : datetime (naïf ou avec fuseau horaire)

    Retourne 0.0 si les prix sont indisponibles.
    """
    if prix is None or prix.empty:
        return 0.0

    try:
        # Convertit dt en Timestamp localisé Europe/Brussels
        horodatage = pandas.Timestamp(dt).tz_localize("Europe/Brussels")
    except TypeError:
        # dt est déjà timezone-aware
        horodatage = pandas.Timestamp(dt).tz_convert("Europe/Brussels")
    except Exception:
        return 0.0
#On convertit dt en timestamp avec le bon fuseau horaire. Deux cas sont gérés :

# Si dt n'a pas de fuseau horaire, tz_localize lui en attribue un
# Si dt en a déjà un, tz_localize lèverait une TypeError — dans ce cas on utilise tz_convert pour le convertir en heure belge
# Si n'importe quoi d'autre plante, on retourne 0.0 par sécurité

    # Cherche le dernier intervalle de prix dont le début est <= horodatage
    valides = prix[prix.index <= horodatage]
    if valides.empty:
        return float(prix.iloc[0])   # premier prix disponible
    return float(valides.iloc[-1])

# prix[prix.index <= horodatage] filtre la série pour ne garder que les prix dont l'heure est avant ou égale à horodatage
# .iloc[-1] prend le dernier élément de cette liste filtrée — c'est donc le prix de la tranche horaire en cours
# Si aucun prix n'est encore passé (la série filtrée est vide), on retourne le tout premier prix disponible avec prix.iloc[0]

def obtenir_prix_negatifs(prix):
    """
    Retourne un pandas.Series contenant uniquement les prix négatifs.
    Retourne une Series vide si aucun prix négatif.
    """
    if prix is None or prix.empty:
        return pandas.Series(dtype=float)
    return prix[prix < 0]
