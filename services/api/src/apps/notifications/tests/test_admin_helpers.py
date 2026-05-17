"""
notifications/tests/test_admin_helpers.py

Tests del helper reutilizable para emails internos del panel ADMIN.

Cubre:
  - Categorías válidas (support, billing, operations, platform_admin).
  - Categoría inválida → False, sin EmailDelivery.
  - Setting vacía → False, sin EmailDelivery.
  - Template por defecto "admin_generic".
  - Template key personalizado.
  - Asociación de related_business y related_user.
  - metadata con admin_category siempre presente.
  - Merge de metadata adicional segura.
  - Filtrado de metadata sensible.
  - Si queue_transactional_email falla → devuelve False, sin propagar excepción.
  - El helper no propaga excepciones.
  - send_async=True por defecto.
  - No usa send_mail ni EmailMessage.
  - Renderiza admin_generic.html sin errores.
  - No envía emails reales en ningún test.
"""
from unittest.mock import MagicMock, call, patch

from django.test import TestCase, override_settings

from apps.notifications.admin_helpers import (
    _SENSITIVE_KEYS,
    _build_metadata,
    _resolve_recipient,
    queue_admin_transactional_email,
)
from apps.notifications.models import EmailDelivery
from apps.notifications.services import render_email_template

_PATCH_TARGET = "apps.notifications.admin_helpers.queue_transactional_email"


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


class ResolveRecipientTest(TestCase):
    """Tests de la función interna _resolve_recipient."""

    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_support_category_returns_support_email(self):
        self.assertEqual(_resolve_recipient("support"), "soporte@mirubro.com")

    @override_settings(BILLING_EMAIL="billing@mirubro.com")
    def test_billing_category_returns_billing_email(self):
        self.assertEqual(_resolve_recipient("billing"), "billing@mirubro.com")

    @override_settings(OPERATIONS_EMAIL="ops@mirubro.com")
    def test_operations_category_returns_operations_email(self):
        self.assertEqual(_resolve_recipient("operations"), "ops@mirubro.com")

    @override_settings(ADMIN_EMAIL="admin@mirubro.com")
    def test_platform_admin_category_returns_admin_email(self):
        self.assertEqual(_resolve_recipient("platform_admin"), "admin@mirubro.com")

    def test_invalid_category_returns_none(self):
        self.assertIsNone(_resolve_recipient("unknown_category"))

    @override_settings(SUPPORT_EMAIL="")
    def test_empty_setting_returns_none(self):
        self.assertIsNone(_resolve_recipient("support"))

    @override_settings(SUPPORT_EMAIL="   ")
    def test_whitespace_only_setting_returns_none(self):
        self.assertIsNone(_resolve_recipient("support"))


class BuildMetadataTest(TestCase):
    """Tests de la función interna _build_metadata."""

    def test_always_includes_admin_category(self):
        meta = _build_metadata("support", None, None, None)
        self.assertIn("admin_category", meta)
        self.assertEqual(meta["admin_category"], "support")

    def test_adds_related_business_id(self):
        mock_business = MagicMock()
        mock_business.pk = 42
        meta = _build_metadata("billing", mock_business, None, None)
        self.assertEqual(meta["related_business_id"], "42")

    def test_adds_related_user_id(self):
        mock_user = MagicMock()
        mock_user.pk = 99
        meta = _build_metadata("operations", None, mock_user, None)
        self.assertEqual(meta["related_user_id"], "99")

    def test_merges_extra_metadata(self):
        meta = _build_metadata("support", None, None, {"ticket_id": "T-001"})
        self.assertEqual(meta["ticket_id"], "T-001")

    def test_filters_token_key(self):
        meta = _build_metadata("support", None, None, {"token": "secret123"})
        self.assertNotIn("token", meta)

    def test_filters_password_key(self):
        meta = _build_metadata("support", None, None, {"password": "abc"})
        self.assertNotIn("password", meta)

    def test_filters_pin_key(self):
        meta = _build_metadata("support", None, None, {"pin": "1234"})
        self.assertNotIn("pin", meta)

    def test_filters_raw_payload_key(self):
        meta = _build_metadata("support", None, None, {"raw_payload": "{...}"})
        self.assertNotIn("raw_payload", meta)

    def test_filters_x_signature_key(self):
        meta = _build_metadata("support", None, None, {"x_signature": "sha256=..."})
        self.assertNotIn("x_signature", meta)

    def test_filters_authorization_key(self):
        meta = _build_metadata("support", None, None, {"authorization": "Bearer xyz"})
        self.assertNotIn("authorization", meta)

    def test_safe_key_is_not_filtered(self):
        meta = _build_metadata("support", None, None, {"event_type": "test"})
        self.assertEqual(meta["event_type"], "test")

    def test_no_business_no_related_business_id(self):
        meta = _build_metadata("support", None, None, None)
        self.assertNotIn("related_business_id", meta)

    def test_no_user_no_related_user_id(self):
        meta = _build_metadata("support", None, None, None)
        self.assertNotIn("related_user_id", meta)


# ---------------------------------------------------------------------------
# Función pública principal
# ---------------------------------------------------------------------------


class QueueAdminTransactionalEmailTest(TestCase):
    """Tests de queue_admin_transactional_email."""

    # --- Categorías válidas ---

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_support_category_calls_queue(self, mock_queue):
        """Categoría support válida: llama a queue_transactional_email."""
        result = queue_admin_transactional_email(
            recipient_category="support",
            subject="Test soporte",
        )
        self.assertTrue(result)
        mock_queue.assert_called_once()
        _, kwargs = mock_queue.call_args
        self.assertEqual(kwargs["to_email"], "soporte@mirubro.com")

    @patch(_PATCH_TARGET)
    @override_settings(BILLING_EMAIL="billing@mirubro.com")
    def test_billing_category_calls_queue(self, mock_queue):
        """Categoría billing válida: llama a queue_transactional_email."""
        result = queue_admin_transactional_email(
            recipient_category="billing",
            subject="Test billing",
        )
        self.assertTrue(result)
        mock_queue.assert_called_once()
        _, kwargs = mock_queue.call_args
        self.assertEqual(kwargs["to_email"], "billing@mirubro.com")

    @patch(_PATCH_TARGET)
    @override_settings(OPERATIONS_EMAIL="ops@mirubro.com")
    def test_operations_category_uses_operations_email(self, mock_queue):
        """Categoría operations usa settings.OPERATIONS_EMAIL."""
        result = queue_admin_transactional_email(
            recipient_category="operations",
            subject="Test ops",
        )
        self.assertTrue(result)
        _, kwargs = mock_queue.call_args
        self.assertEqual(kwargs["to_email"], "ops@mirubro.com")

    @patch(_PATCH_TARGET)
    @override_settings(ADMIN_EMAIL="admin@mirubro.com")
    def test_platform_admin_category_uses_admin_email(self, mock_queue):
        """Categoría platform_admin usa settings.ADMIN_EMAIL."""
        result = queue_admin_transactional_email(
            recipient_category="platform_admin",
            subject="Test admin",
        )
        self.assertTrue(result)
        _, kwargs = mock_queue.call_args
        self.assertEqual(kwargs["to_email"], "admin@mirubro.com")

    # --- Categoría inválida ---

    @patch(_PATCH_TARGET)
    def test_invalid_category_returns_false(self, mock_queue):
        """Categoría inválida: devuelve False sin crear EmailDelivery."""
        result = queue_admin_transactional_email(
            recipient_category="inexistente",
            subject="Test",
        )
        self.assertFalse(result)
        mock_queue.assert_not_called()

    # --- Setting vacía ---

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="")
    def test_empty_setting_returns_false(self, mock_queue):
        """Setting vacía: devuelve False sin llamar queue."""
        result = queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
        )
        self.assertFalse(result)
        mock_queue.assert_not_called()

    # --- Template key ---

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_uses_admin_generic_template_by_default(self, mock_queue):
        """Usa template_key='admin_generic' por defecto."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
        )
        _, kwargs = mock_queue.call_args
        self.assertEqual(kwargs["template_key"], "admin_generic")

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_allows_custom_template_key(self, mock_queue):
        """Permite pasar un template_key personalizado."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
            template_key="mi_template_custom",
        )
        _, kwargs = mock_queue.call_args
        self.assertEqual(kwargs["template_key"], "mi_template_custom")

    # --- Asociación de business y user ---

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_associates_related_business(self, mock_queue):
        """Asocia related_business al pasar business= al queue."""
        mock_business = MagicMock()
        mock_business.pk = 7
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
            related_business=mock_business,
        )
        _, kwargs = mock_queue.call_args
        self.assertIs(kwargs["business"], mock_business)

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_associates_related_user(self, mock_queue):
        """Asocia related_user al pasar user= al queue."""
        mock_user = MagicMock()
        mock_user.pk = 3
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
            related_user=mock_user,
        )
        _, kwargs = mock_queue.call_args
        self.assertIs(kwargs["user"], mock_user)

    # --- metadata ---

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_metadata_always_includes_admin_category(self, mock_queue):
        """La metadata siempre contiene admin_category."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
        )
        _, kwargs = mock_queue.call_args
        self.assertIn("admin_category", kwargs["metadata"])
        self.assertEqual(kwargs["metadata"]["admin_category"], "support")

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_metadata_merges_extra_safe_metadata(self, mock_queue):
        """Mergea metadata adicional segura en la metadata final."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
            metadata={"event_type": "alert", "count": 3},
        )
        _, kwargs = mock_queue.call_args
        self.assertEqual(kwargs["metadata"]["event_type"], "alert")
        self.assertEqual(kwargs["metadata"]["count"], 3)

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_metadata_filters_sensitive_keys(self, mock_queue):
        """Filtra claves sensibles de la metadata recibida."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
            metadata={"token": "secret", "password": "123", "ticket_id": "T-1"},
        )
        _, kwargs = mock_queue.call_args
        meta = kwargs["metadata"]
        self.assertNotIn("token", meta)
        self.assertNotIn("password", meta)
        self.assertIn("ticket_id", meta)

    # --- Comportamiento ante fallo ---

    @patch(_PATCH_TARGET, side_effect=Exception("Celery está caído"))
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_returns_false_if_queue_raises(self, mock_queue):
        """Si queue_transactional_email falla, devuelve False."""
        result = queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
        )
        self.assertFalse(result)

    @patch(_PATCH_TARGET, side_effect=RuntimeError("error inesperado"))
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_does_not_propagate_exceptions(self, mock_queue):
        """El helper no propaga excepciones al caller."""
        try:
            result = queue_admin_transactional_email(
                recipient_category="support",
                subject="Test",
            )
        except Exception as exc:  # pragma: no cover
            self.fail(f"El helper propagó una excepción: {exc}")
        self.assertFalse(result)

    # --- send_async ---

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_send_async_true_by_default(self, mock_queue):
        """send_async=True es el valor por defecto."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
        )
        _, kwargs = mock_queue.call_args
        self.assertTrue(kwargs["send_async"])

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_send_async_false_is_respected(self, mock_queue):
        """send_async=False puede pasarse y es respetado."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
            send_async=False,
        )
        _, kwargs = mock_queue.call_args
        self.assertFalse(kwargs["send_async"])

    # --- No usa send_mail / EmailMessage ---

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    @patch("django.core.mail.send_mail")
    def test_does_not_use_send_mail(self, mock_send_mail, mock_queue):
        """Nunca llama a django.core.mail.send_mail."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
        )
        mock_send_mail.assert_not_called()

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    @patch("django.core.mail.EmailMessage")
    def test_does_not_use_email_message(self, mock_email_msg, mock_queue):
        """Nunca instancia django.core.mail.EmailMessage."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test",
        )
        mock_email_msg.assert_not_called()

    # --- Template admin_generic.html renderiza sin errores ---

    def test_render_admin_generic_template_no_errors(self):
        """admin_generic.html se renderiza sin TemplateDoesNotExist ni errores."""
        context = {
            "title": "Test interno",
            "message": "Mensaje de prueba",
            "details": {"Campo": "Valor"},
            "action_url": "http://localhost:3000/admin",
            "action_label": "Abrir en admin",
        }
        html, text = render_email_template("admin_generic", context)
        self.assertIn("Test interno", html)
        self.assertIn("Mensaje de prueba", html)
        self.assertIn("NOTIFICACIÓN INTERNA", html)

    def test_render_admin_generic_without_optional_fields(self):
        """admin_generic.html no rompe si faltan details y action_url."""
        html, text = render_email_template("admin_generic", {"title": "Solo título"})
        self.assertIn("Solo título", html)
        self.assertIsInstance(html, str)

    # --- No envía emails reales ---

    @patch(_PATCH_TARGET)
    @override_settings(SUPPORT_EMAIL="soporte@mirubro.com")
    def test_no_real_email_sent_in_tests(self, mock_queue):
        """queue_transactional_email es mockeado: no hay envío real de emails."""
        queue_admin_transactional_email(
            recipient_category="support",
            subject="Test sin envío real",
        )
        # El mock fue llamado, pero nunca hubo envío SMTP real.
        self.assertTrue(mock_queue.called)
