from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.business.models import Business, Subscription
from apps.cash.models import CashMovement, CashSession, Payment
from apps.cash.services import compute_session_totals
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
