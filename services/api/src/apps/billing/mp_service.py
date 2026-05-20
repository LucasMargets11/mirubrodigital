import mercadopago
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Global payment-methods configuration for subscription plans
# ─────────────────────────────────────────────────────────────────────────────

def get_mp_subscription_payment_methods_allowed() -> dict:
    """
    Returns the canonical payment_methods_allowed payload for ALL preapproval
    plans created in Mi Rubro.

    Explicitly includes prepaid_card so that cards like Tarjeta Mercado Pago,
    Astro and Lemon are accepted.  Without this field MP defaults to its own
    allow-list, which may exclude prepaid/virtual cards.

    Must be applied to every create_preapproval_plan() call so the config is
    consistent across all products (Gestión Comercial, Carta Online / Menú QR,
    Restaurante Inteligente, QR de Reseñas, future bundles).
    """
    return {
        "payment_types": [
            {"id": "credit_card"},
            {"id": "debit_card"},
            {"id": "prepaid_card"},
        ],
        "payment_methods": [],
    }


class MercadoPagoService:
    def __init__(self):
        self.sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)

    # ── Preapproval plans (subscription plan templates) ───────────────────────

    def create_preapproval_plan(self, reason: str, auto_recurring: dict, back_url: str,
                                 external_reference: str = '') -> dict:
        """
        Creates a preapproval plan (subscription template) in MercadoPago.
        Returns the full MP response dict.

        auto_recurring example::

            {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": 1000,
                "currency_id": "ARS",
            }

        The returned dict contains either ``sandbox_init_point`` (TEST tokens) or
        ``init_point`` (PROD tokens) as the user-facing checkout URL.
        """
        plan_data: dict = {
            "reason": reason,
            "auto_recurring": auto_recurring,
            "back_url": back_url,
            "status": "active",
            "payment_methods_allowed": get_mp_subscription_payment_methods_allowed(),
        }
        if external_reference:
            plan_data["external_reference"] = external_reference

        logger.info(
            "[MPService] create_preapproval_plan payload reason=%r payment_methods_allowed=%s",
            reason, plan_data["payment_methods_allowed"],
        )
        result = self.sdk.plan().create(plan_data)
        if result["status"] == 201:
            logger.info(
                "[MPService] preapproval_plan created id=%s reason=%r",
                result["response"].get("id"), reason,
            )
            return result["response"]
        else:
            logger.error("[MPService] Error creating preapproval_plan: %s", result)
            raise Exception(f"MP plan creation failed: {result}")

    def update_preapproval_plan(self, plan_id: str, update_data: dict) -> dict:
        """
        Updates an existing preapproval plan in MercadoPago.

        Typical usage: patch payment_methods_allowed on a plan that was created
        before this field was introduced, so existing active subscribers accept
        prepaid/virtual cards on their next charge.

        Args:
            plan_id:     The MP preapproval plan ID.
            update_data: Dict with fields to update.

        Returns:
            The MP response dict.

        Raises:
            Exception: If the MP API returns an error.
        """
        result = self.sdk.plan().update(plan_id, update_data)
        if result["status"] == 200:
            logger.info(
                "[MPService] preapproval_plan updated id=%s fields=%s",
                plan_id, list(update_data.keys()),
            )
            return result["response"]
        else:
            logger.error(
                "[MPService] Error updating preapproval_plan %s: %s", plan_id, result,
            )
            raise Exception(f"MP plan update failed: status={result['status']}")

    def get_preapproval_plan(self, plan_id: str) -> dict | None:
        """
        Fetches an authoritative preapproval plan from MP.
        Returns None if not found or on error.
        """
        try:
            result = self.sdk.plan().get(plan_id)
            if result["status"] == 200:
                return result["response"]
            logger.warning("[MPService] get_preapproval_plan %s returned status=%s", plan_id, result["status"])
            return None
        except Exception as exc:
            logger.error("[MPService] get_preapproval_plan error id=%s: %s", plan_id, exc)
            return None

    # ── Preapprovals (user subscriptions to a plan) ───────────────────────────

    def create_preapproval(self, email: str, plan_id: str, external_reference: str,
                           back_url: str) -> dict:
        """
        Creates a subscription (preapproval) enrolling a user to a plan.
        """
        subscription_data = {
            "preapproval_plan_id": plan_id,
            "payer_email": email,
            "external_reference": external_reference,
            "back_url": back_url,
            "status": "pending",
        }
        result = self.sdk.preapproval().create(subscription_data)
        if result["status"] == 201:
            return result["response"]
        else:
            logger.error("[MPService] Error creating preapproval: %s", result)
            raise Exception(f"MP preapproval creation failed: {result}")

    def get_preapproval(self, preapproval_id: str) -> dict | None:
        """
        Fetches an authoritative preapproval (user subscription) from MP.
        Returns None if not found or on error.
        """
        try:
            result = self.sdk.preapproval().get(preapproval_id)
            if result["status"] == 200:
                return result["response"]
            logger.warning(
                "[MPService] get_preapproval %s returned status=%s", preapproval_id, result["status"],
            )
            return None
        except Exception as exc:
            logger.error("[MPService] get_preapproval error id=%s: %s", preapproval_id, exc)
            return None

    def search_preapprovals(self, preapproval_plan_id: str) -> list:
        """
        Search for preapprovals (user subscriptions) linked to a given plan template.

        Used by reconciliation when a user returns from MP before the
        subscription_preapproval webhook fires.

        Returns a list of preapproval dicts (may be empty).
        """
        try:
            result = self.sdk.preapproval().search({
                "preapproval_plan_id": preapproval_plan_id,
            })
            if result["status"] == 200:
                return result["response"].get("results", [])
            logger.warning(
                "[MPService] search_preapprovals plan_id=%s returned status=%s",
                preapproval_plan_id, result["status"],
            )
            return []
        except Exception as exc:
            logger.error(
                "[MPService] search_preapprovals error plan_id=%s: %s", preapproval_plan_id, exc,
            )
            return []

    def search_authorized_payments(self, preapproval_id: str) -> list:
        """
        Search for authorized_payments (recurring charges) linked to a preapproval.

        Used by reconciliation to find the first authorized payment when the
        subscription_authorized_payment webhook has not yet been received.

        Returns a list of authorized_payment dicts (may be empty).
        """
        try:
            result = self.sdk.authorized_payments().search({
                "preapproval_id": preapproval_id,
            })
            if result["status"] == 200:
                return result["response"].get("results", [])
            logger.warning(
                "[MPService] search_authorized_payments preapproval_id=%s returned status=%s",
                preapproval_id, result["status"],
            )
            return []
        except Exception as exc:
            logger.error(
                "[MPService] search_authorized_payments error preapproval_id=%s: %s",
                preapproval_id, exc,
            )
            return []

    def update_preapproval(self, preapproval_id: str, update_data: dict) -> dict:
        """
        Updates a preapproval (user subscription) in MercadoPago.

        Typical usage: cancel a subscription by setting status='cancelled'.

        Args:
            preapproval_id: The MP preapproval ID.
            update_data: Dict with fields to update, e.g. {"status": "cancelled"}.

        Returns:
            The MP response dict.

        Raises:
            Exception: If the MP API returns an error.
        """
        result = self.sdk.preapproval().update(preapproval_id, update_data)
        if result["status"] == 200:
            logger.info(
                "[MPService] preapproval updated id=%s data=%s",
                preapproval_id, {k: v for k, v in update_data.items() if k != 'reason'},
            )
            return result["response"]
        else:
            logger.error(
                "[MPService] Error updating preapproval %s: %s", preapproval_id, result,
            )
            raise Exception(f"MP preapproval update failed: status={result['status']}")

    # ── Authorized payments (recurring charges) ───────────────────────────────

    def get_authorized_payment(self, authorized_payment_id: str) -> dict | None:
        """
        Fetches an authoritative authorized_payment from MP.
        Endpoint: GET /authorized_payments/{id}
        Returns None if not found or on error.
        """
        try:
            result = self.sdk.authorized_payments().get(authorized_payment_id)
            if result["status"] == 200:
                return result["response"]
            logger.warning(
                "[MPService] get_authorized_payment %s returned status=%s",
                authorized_payment_id, result["status"],
            )
            return None
        except Exception as exc:
            logger.error(
                "[MPService] get_authorized_payment error id=%s: %s", authorized_payment_id, exc,
            )
            return None

    # ── One-time payment preferences ─────────────────────────────────────────

    def create_preference(self, items: list, external_reference: str, back_urls: dict,
                          metadata: dict = None) -> dict:
        """
        Creates a one-time payment preference in MercadoPago.

        Args:
            items: List of items [{'title': 'X', 'quantity': 1, 'unit_price': 100}]
            external_reference: Stable reference to track this payment.
            back_urls: Dict with 'success', 'failure', 'pending' URLs.
            metadata: Optional extra metadata dict.

        Returns:
            Response dict with ``init_point`` and ``id`` (preference_id).
        """
        base_public_url = getattr(settings, 'BASE_PUBLIC_URL', None)
        preference_data: dict = {
            "items": items,
            "external_reference": external_reference,
            "back_urls": back_urls,
            "auto_return": "approved",
        }
        if base_public_url:
            preference_data["notification_url"] = (
                f"{base_public_url.rstrip('/')}/api/v1/billing/mercadopago/webhook"
            )
        else:
            logger.warning(
                "[MPService] BASE_PUBLIC_URL not set — notification_url omitted. "
                "Webhooks will NOT fire in DEV.",
            )

        if metadata:
            preference_data["metadata"] = metadata

        result = self.sdk.preference().create(preference_data)
        if result["status"] == 201:
            return result["response"]
        else:
            logger.error("[MPService] Error creating preference: %s", result)
            raise Exception(f"MP preference creation failed: {result}")

    # ── Payments (one-time) ───────────────────────────────────────────────────

    def get_payment(self, payment_id: str) -> dict | None:
        """
        Fetches a payment from MP. Returns None on error/not-found.
        """
        try:
            result = self.sdk.payment().get(payment_id)
            if result["status"] == 200:
                return result["response"]
            logger.warning(
                "[MPService] get_payment %s returned status=%s", payment_id, result["status"],
            )
            return None
        except Exception as exc:
            logger.error("[MPService] get_payment error id=%s: %s", payment_id, exc)
            return None

