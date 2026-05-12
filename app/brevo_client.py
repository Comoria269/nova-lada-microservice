"""
Client Brevo — envoi d'emails transactionnels par template.
"""
import logging
from typing import Any

import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException

from .config import settings

logger = logging.getLogger(__name__)


def _api() -> sib_api_v3_sdk.TransactionalEmailsApi:
    """Construit un client API Brevo configuré."""
    configuration = sib_api_v3_sdk.Configuration()
    configuration.api_key["api-key"] = settings.brevo_api_key
    return sib_api_v3_sdk.TransactionalEmailsApi(
        sib_api_v3_sdk.ApiClient(configuration)
    )


def send_template(
    template_id: int,
    to_email: str,
    to_name: str,
    params: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> str:
    """
    Envoie un template transactionnel Brevo. Retourne le message-id.
    Lève RuntimeError en cas d'échec.

    `headers` permet d'ajouter X-Mailin-Custom (idempotence côté Brevo)
    ou Idempotency-Key (deduplication custom).
    """
    api = _api()
    email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": to_email, "name": to_name}],
        template_id=template_id,
        params=params,
        headers=headers or {},
    )
    try:
        response = api.send_transac_email(email)
        message_id = getattr(response, "message_id", "unknown")
        logger.info(
            "brevo.send_ok",
            extra={
                "template_id": template_id,
                "to": to_email,
                "message_id": message_id,
            },
        )
        return message_id
    except ApiException as e:
        logger.error(
            "brevo.send_fail",
            extra={
                "template_id": template_id,
                "to": to_email,
                "status": e.status,
                "body": e.body,
            },
        )
        raise RuntimeError(f"Brevo send failed (status {e.status})") from e
