"""
tests/test_admin_notification_reviews_integration.py

Integration tests for PR-ADMIN-10E: negative review → AdminNotification.

Covers:
  01. notify_negative_feedback() rating ≤ 3 crea review_negative.
  02. notify_negative_feedback() rating 4 NO crea notificación.
  03. notify_negative_feedback() rating 5 NO crea notificación.
  04. notify_negative_feedback() rating 1 (peor) crea notificación.
  05. notify_negative_feedback() rating exactamente 3 (límite) crea notificación.
  06. La notificación tiene notif_type='review_negative'.
  07. La notificación tiene severity='warning'.
  08. La notificación tiene target_role='support_agent'.
  09. message incluye nombre del negocio y rating.
  10. metadata incluye 'rating' y 'review_id'.
  11. metadata NO incluye el texto completo del comentario.
  12. Si create_admin_notification lanza excepción, notify_negative_feedback no propaga.
  13. Si create_admin_notification lanza excepción, el valor retornado sigue siendo None.
  14. No se usa send_mail.
  15. No se usa EmailMessage.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

_CREATE_NOTIF = 'apps.accounts.admin_notification_service.create_admin_notification'
_NOTIFY_FN = 'apps.reviews.notifications.notify_negative_feedback'


# ── Helper factory ────────────────────────────────────────────────────────────

def _make_review(rating: int):
    business = MagicMock()
    business.id = uuid.uuid4()
    business.name = 'Restaurante El Ñandú'

    review = MagicMock()
    review.id = uuid.uuid4()
    review.rating = rating
    review.comment = 'Servicio muy malo, tardaron demasiado y la comida llegó fría.'
    review.business = business
    review.business_id = business.id
    return review


# ── Tests ─────────────────────────────────────────────────────────────────────

class NotifyNegativeFeedbackTests(SimpleTestCase):
    """Unit tests for notify_negative_feedback()."""

    def _call(self, review, mock_notif):
        """Call notify_negative_feedback with create_admin_notification mocked out."""
        with patch(
            'apps.accounts.admin_notification_service.create_admin_notification',
            mock_notif,
        ):
            from apps.reviews.notifications import notify_negative_feedback
            return notify_negative_feedback(review)

    def test_01_rating_3_creates_notification(self):
        """rating ≤ 3 crea review_negative."""
        review = _make_review(3)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        mock_notif.assert_called_once()

    def test_02_rating_4_does_not_create_notification(self):
        """rating 4 NO crea notificación."""
        review = _make_review(4)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        mock_notif.assert_not_called()

    def test_03_rating_5_does_not_create_notification(self):
        """rating 5 NO crea notificación."""
        review = _make_review(5)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        mock_notif.assert_not_called()

    def test_04_rating_1_creates_notification(self):
        """rating 1 (peor) crea notificación."""
        review = _make_review(1)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        mock_notif.assert_called_once()

    def test_05_rating_3_boundary_creates_notification(self):
        """rating exactamente 3 (límite) crea notificación."""
        review = _make_review(3)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        mock_notif.assert_called_once()

    def test_06_correct_notif_type(self):
        review = _make_review(2)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        self.assertEqual(mock_notif.call_args.kwargs['notif_type'], 'review_negative')

    def test_07_severity_warning(self):
        review = _make_review(2)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        self.assertEqual(mock_notif.call_args.kwargs['severity'], 'warning')

    def test_08_target_role_support_agent(self):
        review = _make_review(2)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        self.assertEqual(mock_notif.call_args.kwargs['target_role'], 'support_agent')

    def test_09_message_includes_business_and_rating(self):
        review = _make_review(2)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        message = mock_notif.call_args.kwargs['message']
        self.assertIn('Restaurante El Ñandú', message)
        self.assertIn('2', message)

    def test_10_metadata_includes_rating_and_review_id(self):
        review = _make_review(2)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        meta = mock_notif.call_args.kwargs['metadata']
        self.assertEqual(meta['rating'], 2)
        self.assertEqual(meta['review_id'], str(review.id))

    def test_11_metadata_does_not_include_full_comment(self):
        """metadata NO incluye el texto completo del comentario."""
        review = _make_review(1)
        mock_notif = MagicMock()
        self._call(review, mock_notif)
        meta = mock_notif.call_args.kwargs['metadata']
        self.assertNotIn('comment', meta)
        self.assertNotIn('Servicio muy malo', str(meta))

    def test_12_exception_does_not_propagate(self):
        """Si create_admin_notification lanza excepción, la función no propaga."""
        review = _make_review(2)
        exploding = MagicMock(side_effect=RuntimeError('Notification DB error'))
        # Should not raise
        self._call(review, exploding)

    def test_13_exception_return_value_is_none(self):
        """Incluso si falla la notificación, el retorno sigue siendo None."""
        review = _make_review(2)
        exploding = MagicMock(side_effect=RuntimeError('Notification DB error'))
        result = self._call(review, exploding)
        self.assertIsNone(result)

    def test_14_no_send_mail_used(self):
        review = _make_review(1)
        mock_notif = MagicMock()
        with patch('django.core.mail.send_mail') as mock_sm:
            self._call(review, mock_notif)
        mock_sm.assert_not_called()

    def test_15_no_email_message_used(self):
        review = _make_review(1)
        mock_notif = MagicMock()
        with patch('django.core.mail.EmailMessage') as mock_em:
            self._call(review, mock_notif)
        mock_em.assert_not_called()
