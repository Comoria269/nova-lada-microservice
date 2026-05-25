"""
NOVA-Lada — Microservice FastAPI pour Lada Vanilia.

Endpoints:
  GET  /health                          → 200 OK (Coolify healthcheck + état Redis)
  POST /webhook/stripe                  → réception webhook Stripe (signé)
  POST /admin/send-shipping             → déclenchement manuel Template 2
  POST /admin/send-review               → déclenchement manuel Template 3
  GET  /admin/ping                      → vérif token admin
"""
import logging
import sys

import redis
import stripe
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_admin_token
from .brevo_client import send_template
from .config import settings
from .stripe_handler import (
    build_confirmation_params,
    get_customer_for_session,
    verify_and_parse,
)

# ─── Logging structuré ──────────────────────────────────────────
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("nova-lada")

# ─── Idempotence durable via Redis (anti double-envoi) ──────────
# Stripe peut renvoyer (retry) un même webhook. On mémorise les
# event_id déjà traités dans Redis, qui survit aux redémarrages du
# conteneur (contrairement à une mémoire interne qui serait vidée).
_redis = redis.from_url(settings.redis_url, decode_responses=True)
_SEEN_KEY = "nova:seen_events"
_SEEN_TTL = 7 * 24 * 3600  # 7 jours : au-delà, aucun retry Stripe possible


def _seen_event(event_id: str) -> bool:
    # SADD renvoie 1 si l'event_id est nouveau, 0 s'il existait déjà.
    is_new = _redis.sadd(_SEEN_KEY, event_id)
    _redis.expire(_SEEN_KEY, _SEEN_TTL)
    return is_new == 0


# ─── App FastAPI ────────────────────────────────────────────────
app = FastAPI(
    title="NOVA-Lada",
    description="Microservice post-purchase pour Lada Vanilia (Stripe → Brevo).",
    version="1.0.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.environment != "production" else None,
)

# CORS — permet à admin.html (ouvert en local ou ailleurs) d'appeler /admin/*.
# Sécurité : les endpoints sont protégés par X-Admin-Token, pas par l'origine.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    # On teste aussi la connexion Redis : utile pour confirmer que
    # l'idempotence est bien opérationnelle (et pour Uptime Kuma).
    try:
        _redis.ping()
        redis_ok = True
    except Exception:
        redis_ok = False
    return {
        "status": "ok",
        "service": "nova-lada",
        "env": settings.environment,
        "redis": redis_ok,
    }


@app.get("/admin/ping", tags=["admin"], dependencies=[Depends(require_admin_token)])
async def admin_ping() -> dict[str, str]:
    return {"status": "ok"}


# ─── Webhook Stripe ─────────────────────────────────────────────
@app.post("/webhook/stripe", tags=["stripe"])
async def stripe_webhook(request: Request) -> dict[str, str]:
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = verify_and_parse(payload, sig_header)
    except ValueError as e:
        logger.warning("stripe.payload_invalid: %s", e)
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError as e:
        logger.warning("stripe.signature_invalid: %s", e)
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_id = event.get("id", "unknown")
    event_type = event.get("type", "unknown")
    logger.info("stripe.event_received id=%s type=%s", event_id, event_type)

    # Idempotence
    if _seen_event(event_id):
        logger.info("stripe.event_duplicate id=%s — skipping", event_id)
        return {"status": "duplicate"}

    # On ne traite que la fin d'un Checkout (Payment Links déclenchent cet event)
    if event_type != "checkout.session.completed":
        logger.info("stripe.event_ignored type=%s", event_type)
        return {"status": "ignored"}

    session_obj = event["data"]["object"]
    # Le webhook donne un objet partiel ; on récupère la session complète
    # (utile pour customer_details si pas inclus dans le payload)
    session = stripe.checkout.Session.retrieve(
        session_obj["id"],
        expand=["customer_details"],
    )

    try:
        params = build_confirmation_params(session)
    except ValueError as e:
        logger.error("stripe.params_build_fail: %s", e)
        # On répond 200 pour ne pas que Stripe retry inutilement —
        # le problème est dans nos données, pas dans la livraison du webhook.
        return {"status": "missing_data", "detail": str(e)}

    to_email = params["email"]
    to_name = f"{params['prenom']} {params['nom']}".strip() or to_email

    try:
        message_id = send_template(
            settings.brevo_template_confirmation_id,
            to_email=to_email,
            to_name=to_name,
            params=params,
            headers={"X-Mailin-Custom": f"stripe_event:{event_id}"},
        )
    except RuntimeError as e:
        logger.error("brevo.send_fail event_id=%s: %s", event_id, e)
        # 500 pour que Stripe retry
        raise HTTPException(status_code=500, detail="Email send failed")

    logger.info(
        "confirmation.sent event_id=%s session=%s to=%s message_id=%s",
        event_id, session.id, to_email, message_id,
    )
    return {"status": "sent", "message_id": message_id}


# ─── Endpoints admin (Templates 2 & 3 déclenchés manuellement) ──
@app.post(
    "/admin/send-shipping",
    tags=["admin"],
    dependencies=[Depends(require_admin_token)],
)
async def send_shipping(payload: dict) -> dict[str, str]:
    """
    Déclenche le Template 2 (Expédition) pour un client.

    Body JSON attendu :
      {
        "session_id":   "cs_xxx",          # OU "email" + "prenom" en mode manuel
        "email":        "client@x.fr",     # optionnel si session_id fourni
        "prenom":       "Marie",           # optionnel
        "commande_id":  "ABC12345",
        "numero_suivi": "8L12345678901"
      }
    """
    commande_id = payload.get("commande_id")
    numero_suivi = payload.get("numero_suivi")
    if not commande_id or not numero_suivi:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="commande_id et numero_suivi requis",
        )

    if session_id := payload.get("session_id"):
        try:
            email, name = get_customer_for_session(session_id)
        except (stripe.error.StripeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Session Stripe introuvable: {e}")
        prenom = name.split(maxsplit=1)[0] if name else "client"
    else:
        email = payload.get("email")
        prenom = payload.get("prenom") or "client"
        if not email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Fournir 'session_id' OU 'email' + 'prenom'",
            )
        name = prenom

    params = {
        "prenom": prenom,
        "commande_id": commande_id,
        "numero_suivi": numero_suivi,
    }

    message_id = send_template(
        settings.brevo_template_expedition_id,
        to_email=email,
        to_name=name,
        params=params,
    )
    logger.info("expedition.sent to=%s commande=%s suivi=%s", email, commande_id, numero_suivi)
    return {"status": "sent", "message_id": message_id}


@app.post(
    "/admin/send-review",
    tags=["admin"],
    dependencies=[Depends(require_admin_token)],
)
async def send_review(payload: dict) -> dict[str, str]:
    """
    Déclenche le Template 3 (Demande d'avis) pour un client.

    Body JSON attendu :
      {
        "email":  "client@x.fr",
        "prenom": "Marie"
      }
    """
    email = payload.get("email")
    prenom = payload.get("prenom") or "client"
    if not email:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="email requis",
        )

    message_id = send_template(
        settings.brevo_template_avis_id,
        to_email=email,
        to_name=prenom,
        params={"prenom": prenom},
    )
    logger.info("review.sent to=%s", email)
    return {"status": "sent", "message_id": message_id}
    return {"status": "sent", "message_id": message_id}
