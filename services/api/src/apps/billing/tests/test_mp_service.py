"""Contract tests for Mercado Pago preapproval plan payment types."""

from itertools import count
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.billing.canonical_pricing import plan_price
from apps.billing.checkout_session_service import start_checkout
from apps.billing.models import MpCheckoutSession, Plan
from apps.billing.mp_service import MercadoPagoService


PAYMENT_METHODS_ALLOWED = {
    "payment_types": [
        {"id": "account_money"},
        {"id": "credit_card"},
        {"id": "debit_card"},
    ],
    "payment_methods": [],
}


class PreapprovalPlanPayloadTest(SimpleTestCase):
    @patch("apps.billing.mp_service.mercadopago.SDK")
    def test_create_preapproval_plan_preserves_payload_contract(self, sdk_class):
        sdk = sdk_class.return_value
        sdk.plan.return_value.create.return_value = {
            "status": 201,
            "response": {"id": "MP-PLAN-1"},
        }
        auto_recurring = {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": 36000.0,
            "currency_id": "ARS",
        }

        result = MercadoPagoService().create_preapproval_plan(
            reason="Suscripción a Gestión",
            auto_recurring=auto_recurring,
            back_url="https://app.test/subscribe/return",
            external_reference="SESS-123",
        )

        self.assertEqual(result, {"id": "MP-PLAN-1"})
        sdk.plan.return_value.create.assert_called_once_with({
            "reason": "Suscripción a Gestión",
            "auto_recurring": auto_recurring,
            "back_url": "https://app.test/subscribe/return",
            "status": "active",
            "payment_methods_allowed": PAYMENT_METHODS_ALLOWED,
            "external_reference": "SESS-123",
        })
        payload = sdk.plan.return_value.create.call_args.args[0]
        self.assertEqual(
            [item["id"] for item in payload["payment_methods_allowed"]["payment_types"]],
            ["account_money", "credit_card", "debit_card"],
        )
        self.assertNotIn("prepaid_card", str(payload))

    @patch("apps.billing.mp_service.mercadopago.SDK")
    def test_external_reference_stays_optional(self, sdk_class):
        sdk = sdk_class.return_value
        sdk.plan.return_value.create.return_value = {
            "status": 201,
            "response": {"id": "MP-PLAN-2"},
        }

        MercadoPagoService().create_preapproval_plan(
            reason="Plan",
            auto_recurring={"frequency": 1},
            back_url="https://app.test/return",
        )

        payload = sdk.plan.return_value.create.call_args.args[0]
        self.assertEqual(payload["payment_methods_allowed"], PAYMENT_METHODS_ALLOWED)
        self.assertNotIn("external_reference", payload)


class SharedCheckoutPreapprovalContractTest(TestCase):
    @patch("apps.billing.mp_service.mercadopago.SDK")
    def test_gestion_menu_qr_and_qr_reviews_use_same_valid_contract(self, sdk_class):
        user = get_user_model().objects.create_user(
            username="mp-plan-contract@test.com",
            email="mp-plan-contract@test.com",
            password="testpass1234",
        )
        cases = (
            ("gestion_start", "Gestión"),
            ("menu_qr_basico", "Menú QR"),
            ("qr_reviews_base", "QR Reseñas"),
        )
        sdk = sdk_class.return_value
        plan_ids = count(1)
        sdk.plan.return_value.create.side_effect = lambda _payload: {
            "status": 201,
            "response": {
                "id": f"MP-PLAN-{next(plan_ids)}",
                "init_point": "https://mp.test/subscribe",
            },
        }

        for code, name in cases:
            Plan.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "price": plan_price(code),
                    "interval": "monthly",
                    "currency": "ARS",
                    "frequency": 1,
                    "frequency_type": "months",
                    "plan_status": "active",
                },
            )
            start_checkout(
                user=user,
                tenant=None,
                plan_code=code,
                frontend_url="https://app.test",
            )

        calls = sdk.plan.return_value.create.call_args_list
        self.assertEqual(len(calls), len(cases))
        for (code, name), call in zip(cases, calls):
            with self.subTest(plan=code):
                session = MpCheckoutSession.objects.get(plan__code=code)
                self.assertEqual(call.args[0], {
                    "reason": f"Suscripción a {name}",
                    "auto_recurring": {
                        "frequency": 1,
                        "frequency_type": "months",
                        "transaction_amount": float(plan_price(code)),
                        "currency_id": "ARS",
                    },
                    "back_url": (
                        "https://app.test/subscribe/return"
                        f"?checkout_session_id={session.id}"
                    ),
                    "status": "active",
                    "payment_methods_allowed": PAYMENT_METHODS_ALLOWED,
                    "external_reference": session.mp_external_reference,
                })
                self.assertNotIn("prepaid_card", str(call.args[0]))
