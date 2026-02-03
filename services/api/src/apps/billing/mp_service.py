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
