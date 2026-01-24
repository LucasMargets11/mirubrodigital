from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.business.models import Business, Subscription
from apps.cash.models import CashMovement, CashSession, Payment
from apps.cash.serializers import CashSessionCloseSerializer
from apps.cash.services import collect_pending_session_sales, compute_session_totals
from apps.sales.models import Sale


class CashServicesTests(TestCase):
  def setUp(self):
    self.user = get_user_model().objects.create_user(username='cashier', email='cashier@example.com', password='pass1234')
    self.business = Business.objects.create(name='Caja Biz')
    Subscription.objects.create(business=self.business, plan='starter', status='active')
    self.session = CashSession.objects.create(
      business=self.business,
      opened_by=self.user,
      opening_cash_amount=Decimal('100.00'),
    )
    self.sale = Sale.objects.create(
      business=self.business,
      number=1,
      subtotal=Decimal('0.00'),
      discount=Decimal('0.00'),
      total=Decimal('0.00'),
    )

  def test_compute_session_totals_tracks_cash_expectation(self):
    Payment.objects.create(
      business=self.business,
      sale=self.sale,
      session=self.session,
      method=Payment.Method.CASH,
      amount=Decimal('150.00'),
    )
    Payment.objects.create(
      business=self.business,
      sale=self.sale,
      session=self.session,
      method=Payment.Method.CREDIT,
      amount=Decimal('300.00'),
    )
    CashMovement.objects.create(
      business=self.business,
      session=self.session,
      movement_type=CashMovement.MovementType.IN,
      category=CashMovement.Category.DEPOSIT,
      method=Payment.Method.CASH,
      amount=Decimal('50.00'),
    )
    CashMovement.objects.create(
      business=self.business,
      session=self.session,
      movement_type=CashMovement.MovementType.OUT,
      category=CashMovement.Category.WITHDRAW,
      method=Payment.Method.CASH,
      amount=Decimal('20.00'),
    )

    totals = compute_session_totals(self.session)

    self.assertEqual(totals['payments_total'], Decimal('450.00'))
    self.assertEqual(totals['cash_payments_total'], Decimal('150.00'))
    self.assertEqual(totals['movements_in_total'], Decimal('50.00'))
    self.assertEqual(totals['movements_out_total'], Decimal('20.00'))
    self.assertEqual(totals['cash_expected_total'], Decimal('280.00'))
    self.assertEqual(totals['payments_by_method'][Payment.Method.CASH], Decimal('150.00'))
    self.assertEqual(totals['sales_count'], 1)

  def test_collect_pending_session_sales_is_idempotent(self):
    sale = Sale.objects.create(
      business=self.business,
      number=2,
      subtotal=Decimal('0.00'),
      discount=Decimal('0.00'),
      total=Decimal('200.00'),
    )

    first_result = collect_pending_session_sales(self.session, user=self.user)
    self.assertEqual(first_result['collected_count'], 1)
    self.assertEqual(first_result['skipped_count'], 0)

    second_result = collect_pending_session_sales(self.session, user=self.user)
    self.assertEqual(second_result['collected_count'], 0)
    self.assertGreaterEqual(second_result['skipped_count'], 1)

  def test_collect_pending_includes_sales_linked_to_session_even_outside_range(self):
    sale = Sale.objects.create(
      business=self.business,
      number=3,
      subtotal=Decimal('0.00'),
      discount=Decimal('0.00'),
      total=Decimal('120.00'),
      cash_session=self.session,
    )
    Sale.objects.filter(pk=sale.pk).update(created_at=self.session.opened_at - timedelta(days=2))

    result = collect_pending_session_sales(self.session, user=self.user)

    self.assertEqual(result['collected_count'], 1)
    self.assertIn(str(sale.id), result['sale_ids'])

  def test_close_session_collects_pending_when_flag_enabled(self):
    sale_partial = Sale.objects.create(
      business=self.business,
      number=2,
      subtotal=Decimal('0.00'),
      discount=Decimal('0.00'),
      total=Decimal('300.00'),
    )
    Payment.objects.create(
      business=self.business,
      sale=sale_partial,
      session=self.session,
      method=Payment.Method.CASH,
      amount=Decimal('100.00'),
    )
    sale_pending = Sale.objects.create(
      business=self.business,
      number=3,
      subtotal=Decimal('0.00'),
      discount=Decimal('0.00'),
      total=Decimal('150.00'),
    )
    Sale.objects.create(
      business=self.business,
      number=4,
      subtotal=Decimal('0.00'),
      discount=Decimal('0.00'),
      total=Decimal('90.00'),
      status=Sale.Status.CANCELLED,
    )

    serializer = CashSessionCloseSerializer(
      data={
        'closing_cash_counted': Decimal('540.00'),
        'note': 'Cierre turno mañana',
        'collect_pending_sales': True,
      },
      context={'session': self.session, 'user': self.user},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()

    self.session.refresh_from_db()
    data = serializer.data
    summary = data['collection_summary']

    self.assertIsNotNone(summary)
    self.assertEqual(summary['collected_count'], 2)
    self.assertEqual(summary['skipped_count'], 0)
    self.assertEqual(summary['sale_ids'], [str(sale_partial.id), str(sale_pending.id)])
    self.assertEqual(summary['errors'], [])
    self.assertEqual(str(summary['total_collected']), '350.00')

    self.assertEqual(Payment.objects.filter(session=self.session).count(), 3)
    self.assertEqual(self.session.status, CashSession.Status.CLOSED)

    payload_session = data['session']
    self.assertEqual(payload_session['status'], CashSession.Status.CLOSED)
    self.assertEqual(payload_session['totals']['pending_sales_count'], 0)

    difference_value = Decimal(payload_session['difference_amount'])
    self.assertEqual(difference_value, Decimal('540.00') - Decimal(payload_session['expected_cash_total']))

  def test_close_session_without_collection_flag_keeps_sales_pending(self):
    sale_pending = Sale.objects.create(
      business=self.business,
      number=5,
      subtotal=Decimal('0.00'),
      discount=Decimal('0.00'),
      total=Decimal('180.00'),
    )

    serializer = CashSessionCloseSerializer(
      data={
        'closing_cash_counted': Decimal('280.00'),
        'note': '',
        'collect_pending_sales': False,
      },
      context={'session': self.session, 'user': self.user},
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()

    sale_pending.refresh_from_db()
    self.assertEqual(Payment.objects.filter(sale=sale_pending).count(), 0)
    self.assertEqual(self.session.payments.count(), 0)
    self.assertIsNone(serializer.data['collection_summary'])
