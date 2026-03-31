

import pandas
#tableau donnés 
from datetime import datetime

try:
    from entsoe import EntsoePandasClient
    ENTSOE_DISPONIBLE = True
except ImportError:
    ENTSOE_DISPONIBLE = False
#démarrer quand même et d'afficher un message d'erreur

import config


def recuperer_prix_journaliers(date=None): #si date est None, on prend la date du jour

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

#query_day_ahead_prices methode pour recup prix

def obtenir_prix_a_instant(prix, dt):

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


    # Cherche le dernier intervalle de prix dont le début est <= horodatage
    valides = prix[prix.index <= horodatage]
    if valides.empty:
        return float(prix.iloc[0])   # premier prix disponible
    return float(valides.iloc[-1])


def obtenir_prix_negatifs(prix): #retourne une série ne contenant que les prix négatifs
    
    if prix is None or prix.empty:
        return pandas.Series(dtype=float)
    return prix[prix < 0]
