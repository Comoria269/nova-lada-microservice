"""
Utilitaires de date en français.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"
]

PARIS_TZ = ZoneInfo("Europe/Paris")


def format_date_fr(d: date) -> str:
    """Formate une date en français : 12 mai 2026."""
    return f"{d.day} {MOIS_FR[d.month - 1]} {d.year}"


def now_paris() -> datetime:
    """Datetime courant en heure de Paris."""
    return datetime.now(PARIS_TZ)


def add_business_days(start: date, n: int) -> date:
    """Ajoute n jours ouvrés (lundi-vendredi) à une date."""
    d = start
    added = 0
    while added < n:
        d += timedelta(days=1)
        if d.weekday() < 5:  # 0=lundi, 4=vendredi
            added += 1
    return d


def format_montant_eur(cents: int) -> str:
    """Formate des centimes en montant euro français : '39.90'."""
    return f"{cents / 100:.2f}"
