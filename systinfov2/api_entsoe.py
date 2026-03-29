# ==============================================================================
# api_entsoe.py - Récupération des prix d'électricité via l'API ENTSO-E
#
# Utilise la librairie entsoe-py (pip install entsoe-py)
# Documentation : https://github.com/EnergieID/entsoe-py
# ==============================================================================

import pandas as pd
#: une librairie pour manipuler des tableaux de données. Ici on l'utilise pour stocker les prix sous forme de série temporelle (une valeur par heure).
from datetime import datetime

try:
    from entsoe import EntsoePandasClient
    ENTSOE_AVAILABLE = True
except ImportError:
    ENTSOE_AVAILABLE = False

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
    if not ENTSOE_AVAILABLE:
        raise ImportError(
            "La librairie entsoe-py n'est pas installée.\n"
            "Exécutez : pip install entsoe-py"
        )

    client = EntsoePandasClient(api_key=config.ENTSOE_TOKEN)

    if date is None:
        date = datetime.now()

    # Début et fin de la journée en heure locale belge
    start = pd.Timestamp(date.strftime("%Y%m%d"), tz="Europe/Brussels")
    end   = start + pd.Timedelta(days=1)

    prices = client.query_day_ahead_prices(config.COUNTRY_CODE, start=start, end=end)
    return prices


def obtenir_prix_a_instant(prices, dt):
    """
    Retourne le prix de l'électricité (EUR/MWh) à un instant donné.

    Paramètres :
        prices : pandas.Series retourné par recuperer_prix_journaliers()
        dt     : datetime (naïf ou avec fuseau horaire)

    Retourne 0.0 si les prix sont indisponibles.
    """
    if prices is None or prices.empty:
        return 0.0

    try:
        # Convertit dt en Timestamp localisé Europe/Brussels
        ts = pd.Timestamp(dt).tz_localize("Europe/Brussels")
    except TypeError:
        # dt est déjà timezone-aware
        ts = pd.Timestamp(dt).tz_convert("Europe/Brussels")
    except Exception:
        return 0.0

    # Cherche le dernier intervalle de prix dont le début est <= ts
    valid = prices[prices.index <= ts]
    if valid.empty:
        return float(prices.iloc[0])   # premier prix disponible
    return float(valid.iloc[-1])


def obtenir_prix_negatifs(prices):
    """
    Retourne un pandas.Series contenant uniquement les prix négatifs.
    Retourne une Series vide si aucun prix négatif.
    """
    if prices is None or prices.empty:
        return pd.Series(dtype=float)
    return prices[prices < 0]
