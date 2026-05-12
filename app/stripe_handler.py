"""
Stripe — validation des webhooks + extraction des données de commande.
"""
import logging
from typing import Any

import stripe

from .config import settings
from .date_utils import format_date_fr, format_montant_eur, add_business_days, now_paris

logger = logging.getLogger(__name__)

stripe.api_key = settings.stripe_api_key


def verify_and_parse(payload: bytes, sig_header: str) -> stripe.Event:
    """
    Valide la signature du webhook Stripe.
    Lève stripe.SignatureVerificationError si invalide.
    """
    return stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )


def _extract_first_last(full_name: str | None) -> tuple[str, str]:
    """Sépare 'Marie Dupont' → ('Marie', 'Dupont'). Fallback gracieux."""
    if not full_name:
        return ("", "")
    parts = full_name.strip().split(maxsplit=1)
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], parts[1])


def build_confirmation_params(session: stripe.checkout.Session) -> dict[str, Any]:
    """
    Construit le dict `params` Brevo pour le Template 1 (Confirmation).
    Lève ValueError si infos manquantes.
    """
    details = session.customer_details or {}
    email = getattr(details, "email", None) or session.customer_email
    if not email:
        raise ValueError("Email client manquant dans la session Stripe")

    name = getattr(details, "name", None) or ""
    prenom, nom = _extract_first_last(name)

    # Récupère les line items (séparé de l'objet session)
    line_items = stripe.checkout.Session.list_line_items(session.id, limit=100)
    items_html_parts: list[str] = []
    for li in line_items.auto_paging_iter():
        desc = li.description or "Produit"
        qty = li.quantity or 1
        unit_eur = format_montant_eur(li.price.unit_amount or 0)
        items_html_parts.append(
            f"<li>{desc} — {qty} × {unit_eur} €</li>"
        )
    liste_produits = "<ul>" + "".join(items_html_parts) + "</ul>" if items_html_parts else ""

    amount_total = session.amount_total or 0
    today = now_paris().date()
    livraison = add_business_days(today, settings.default_shipping_days)

    # `commande_id` plus court pour le client : 8 derniers caractères du PI
    pi_id = session.payment_intent or session.id
    commande_id_short = pi_id[-8:].upper() if isinstance(pi_id, str) else str(pi_id)

    return {
        "prenom": prenom or "client",
        "nom": nom,
        "email": email,
        "commande_id": commande_id_short,
        "date": format_date_fr(today),
        "montant": format_montant_eur(amount_total),
        "liste_produits": liste_produits,
        "date_livraison": format_date_fr(livraison),
    }


def get_customer_for_session(session_id: str) -> tuple[str, str]:
    """Retourne (email, name) pour une session donnée. Utilisé par /admin endpoints."""
    session = stripe.checkout.Session.retrieve(session_id)
    details = session.customer_details or {}
    email = getattr(details, "email", None) or session.customer_email
    name = getattr(details, "name", None) or ""
    if not email:
        raise ValueError(f"Aucun email pour session {session_id}")
    return email, name
