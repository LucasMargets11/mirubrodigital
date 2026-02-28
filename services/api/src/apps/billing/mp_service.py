import mercadopago
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class MercadoPagoService:
    def __init__(self):
        self.sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)

    def create_preapproval_plan(self, reason: str, auto_recurring: dict, back_url: str):
        """
        Creates a preapproval plan (subscriptions plan) in MercadoPago.
        auto_recurring: {'frequency': 1, 'frequency_type': 'months', 'transaction_amount': 1000, 'currency_id': 'ARS'}
        """
        plan_data = {
            "reason": reason,
            "auto_recurring": auto_recurring,
            "back_url": back_url,
            "status": "active"
        }
        
        result = self.sdk.preapproval_plan().create(plan_data)
        if result["status"] == 201:
            return result["response"]
        else:
            logger.error(f"Error creating MP plan: {result}")
            # Depending on error structure, might need adjustments
            raise Exception(f"Error creating MP plan: {result}")

    def create_preapproval(self, email: str, plan_id: str, external_reference: str, back_url: str):
        """
        Creates a subscription (preapproval) for a user to a plan.
        """
        subscription_data = {
            "preapproval_plan_id": plan_id,
            "payer_email": email,
            "external_reference": external_reference,
            "back_url": back_url,
            "status": "pending"
        }
        
        result = self.sdk.preapproval().create(subscription_data)
        if result["status"] == 201:
            return result["response"]
        else:
            logger.error(f"Error creating MP preapproval: {result}")
            raise Exception(f"Error creating MP preapproval: {result}")
    
    def get_preapproval(self, id: str):
        result = self.sdk.preapproval().get(id)
        if result["status"] == 200:
            return result["response"]
        return None

    def create_preference(self, items: list, external_reference: str, back_urls: dict, metadata: dict = None):
        """
        Creates a one-time payment preference in MercadoPago.
        
        Args:
            items: List of items [{'title': 'X', 'quantity': 1, 'unit_price': 100}]
            external_reference: Reference ID to track this payment
            back_urls: Dict with 'success', 'failure', 'pending' URLs
            metadata: Optional metadata dict
        
        Returns:
            Response dict with init_point and preference_id
        """
        # BASE_PUBLIC_URL must be the externally-reachable URL of the *API* server
        # (e.g. ngrok in DEV, real domain in prod). Never use the frontend URL here —
        # MP sends webhook POST requests to this address, and they must reach Django.
        # If not set, omit notification_url so the app still works (no webhooks in DEV).
        base_public_url = getattr(settings, 'BASE_PUBLIC_URL', None)
        preference_data = {
            "items": items,
            "external_reference": external_reference,
            "back_urls": back_urls,
            "auto_return": "approved",
        }
        if base_public_url:
            preference_data["notification_url"] = f"{base_public_url.rstrip('/')}/api/v1/billing/mercadopago/webhook"
        else:
            logger.warning("[MPService] BASE_PUBLIC_URL not set — notification_url omitted. Webhooks will NOT fire in DEV.")
        
        if metadata:
            preference_data["metadata"] = metadata
        
        result = self.sdk.preference().create(preference_data)
        if result["status"] == 201:
            return result["response"]
        else:
            logger.error(f"Error creating MP preference: {result}")
            raise Exception(f"Error creating MP preference: {result}")
