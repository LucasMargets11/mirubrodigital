"""Tests for customer history endpoints (sales and quotes)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Membership
from apps.business.models import Business, Subscription
from apps.customers.models import Customer
from apps.sales.models import Quote, QuoteItem, Sale, SaleItem


class CustomerHistoryAPITests(APITestCase):
    """Tests for GET /api/v1/customers/{id}/sales/ and /quotes/."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='manager_test', email='manager@example.com', password='pass1234'
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _create_business(self, name: str = 'Negocio Test') -> Business:
        business = Business.objects.create(name=name)
        Subscription.objects.create(business=business, plan='starter', status='active')
        return business

    def _authenticate(self, business: Business, role: str = 'manager'):
        Membership.objects.filter(user=self.user).delete()
        Membership.objects.create(user=self.user, business=business, role=role)
        self.client.force_authenticate(user=self.user)
        self.client.cookies['bid'] = str(business.id)

    def _create_customer(self, business: Business, name: str = 'Cliente Test') -> Customer:
        return Customer.objects.create(business=business, name=name)

    def _create_sale(self, business: Business, customer: Customer | None = None) -> Sale:
        number = Sale.objects.filter(business=business).count() + 1
        return Sale.objects.create(
            business=business,
            customer=customer,
            number=number,
            subtotal=Decimal('100'),
            discount=Decimal('0'),
            total=Decimal('100'),
            payment_method=Sale.PaymentMethod.CASH,
        )

    def _create_quote(self, business: Business, customer: Customer | None = None) -> Quote:
        number = f"P-{Quote.objects.filter(business=business).count() + 1:06d}"
        quote = Quote.objects.create(
            business=business,
            customer=customer,
            number=number,
            customer_name=customer.name if customer else 'Anónimo',
        )
        QuoteItem.objects.create(
            quote=quote,
            name_snapshot='Producto',
            quantity=Decimal('1'),
            unit_price=Decimal('50'),
            discount=Decimal('0'),
            total_line=Decimal('50'),
        )
        return quote

    # ── Customer Sales Tests ─────────────────────────────────────────────────

    def test_customer_sales_returns_associated_sale(self):
        """Creating a sale with a customer returns it in /customers/{id}/sales/."""
        business = self._create_business()
        self._authenticate(business)
        customer = self._create_customer(business)
        self._create_sale(business, customer=customer)

        url = reverse('customers:customer-sales', kwargs={'pk': str(customer.id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        result = response.data['results'][0]
        self.assertEqual(result['customer_id'], str(customer.id))

    def test_customer_sales_excludes_sales_from_other_customers(self):
        """Sales assigned to another customer are not returned."""
        business = self._create_business()
        self._authenticate(business)
        customer_a = self._create_customer(business, 'Cliente A')
        customer_b = self._create_customer(business, 'Cliente B')
        self._create_sale(business, customer=customer_a)
        self._create_sale(business, customer=customer_b)

        url = reverse('customers:customer-sales', kwargs={'pk': str(customer_a.id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_customer_sales_empty_when_no_sales(self):
        """Returns empty list if customer has no sales."""
        business = self._create_business()
        self._authenticate(business)
        customer = self._create_customer(business)

        url = reverse('customers:customer-sales', kwargs={'pk': str(customer.id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)
        self.assertEqual(response.data['results'], [])

    def test_customer_sales_scoped_to_tenant(self):
        """Customer from another business returns 404."""
        business_a = self._create_business('Negocio A')
        business_b = self._create_business('Negocio B')
        self._authenticate(business_a)
        customer_b = self._create_customer(business_b, 'Cliente de B')

        url = reverse('customers:customer-sales', kwargs={'pk': str(customer_b.id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_customer_sales_requires_business_membership(self):
        """User with no membership in the business gets 403."""
        business = self._create_business()
        customer = self._create_customer(business)
        # Authenticate to a different business only
        other_business = self._create_business('Otro Negocio')
        self._authenticate(other_business, role='manager')

        url = reverse('customers:customer-sales', kwargs={'pk': str(customer.id)})
        response = self.client.get(url)

        # Customer belongs to a different business → 404 (scoping) or 403
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_customer_sales_requires_authentication(self):
        """Anonymous user gets 401."""
        business = self._create_business()
        customer = self._create_customer(business)
        self.client.logout()

        url = reverse('customers:customer-sales', kwargs={'pk': str(customer.id)})
        response = self.client.get(url)

        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    # ── Customer Quotes Tests ────────────────────────────────────────────────

    def test_customer_quotes_returns_associated_quote(self):
        """Creating a quote with a customer returns it in /customers/{id}/quotes/."""
        business = self._create_business()
        self._authenticate(business)
        customer = self._create_customer(business)
        self._create_quote(business, customer=customer)

        url = reverse('customers:customer-quotes', kwargs={'pk': str(customer.id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        result = response.data['results'][0]
        self.assertEqual(result['customer_id'], str(customer.id))

    def test_customer_quotes_excludes_deleted_quotes(self):
        """Soft-deleted quotes are excluded from the list."""
        business = self._create_business()
        self._authenticate(business)
        customer = self._create_customer(business)
        quote = self._create_quote(business, customer=customer)
        quote.is_deleted = True
        quote.save(update_fields=['is_deleted'])

        url = reverse('customers:customer-quotes', kwargs={'pk': str(customer.id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_customer_quotes_scoped_to_tenant(self):
        """Customer from another business returns 404."""
        business_a = self._create_business('Negocio A')
        business_b = self._create_business('Negocio B')
        self._authenticate(business_a)
        customer_b = self._create_customer(business_b, 'Cliente de B')

        url = reverse('customers:customer-quotes', kwargs={'pk': str(customer_b.id)})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_customer_quotes_requires_business_membership(self):
        """User with no membership in the business gets 403 / 404."""
        business = self._create_business()
        customer = self._create_customer(business)
        other_business = self._create_business('Otro Negocio')
        self._authenticate(other_business, role='manager')

        url = reverse('customers:customer-quotes', kwargs={'pk': str(customer.id)})
        response = self.client.get(url)

        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_quote_with_customer_id_links_to_customer(self):
        """Quote created with customer_id has correct FK relationship."""
        business = self._create_business()
        customer = self._create_customer(business)
        quote = self._create_quote(business, customer=customer)

        self.assertEqual(quote.customer_id, customer.id)
        self.assertEqual(quote.customer.name, customer.name)

    def test_sale_with_customer_id_links_to_customer(self):
        """Sale FK to customer is correctly set."""
        business = self._create_business()
        customer = self._create_customer(business)
        sale = self._create_sale(business, customer=customer)

        self.assertEqual(sale.customer_id, customer.id)
        self.assertQuerySetEqual(
            customer.sales.all(),
            Sale.objects.filter(pk=sale.pk),
        )
