"""
catalog/pos_views.py — POS operative endpoints for product catalog.

Routes:
  GET /api/v1/pos/catalog/products/   — search / browse active products
  GET /api/v1/pos/catalog/categories/ — list active categories with product counts

Auth: EmployeeTokenAuthentication + PinChangeNotRequired
Capability: none (any authenticated, pin-cleared employee can browse products)

This endpoint exists because admin product routes use cookie-based auth
(IsAuthenticated + HasBusinessMembership).  The POS terminal needs product
data via X-Employee-Token for the sale creation form.
"""
from __future__ import annotations

import uuid as uuid_module

from django.db.models import Count, Q
from rest_framework import serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import EmployeeTokenAuthentication
from apps.accounts.permissions import EmployeeIsAuthenticated, PinChangeNotRequired
from apps.inventory.services import ensure_stock_record

from .models import Product, ProductCategory


class PosProductSerializer(drf_serializers.Serializer):
    """Minimal product representation for POS sale creation."""

    id = drf_serializers.UUIDField()
    name = drf_serializers.CharField()
    sku = drf_serializers.CharField()
    price = drf_serializers.DecimalField(max_digits=12, decimal_places=2)
    stock_quantity = drf_serializers.SerializerMethodField()
    stock_min = drf_serializers.DecimalField(max_digits=12, decimal_places=2)
    category_id = drf_serializers.SerializerMethodField()
    is_active = drf_serializers.BooleanField()

    def get_stock_quantity(self, obj: Product) -> str:
        business = self.context.get('business') or obj.business
        stock = ensure_stock_record(business, obj)
        return str(stock.quantity)

    def get_category_id(self, obj: Product) -> str | None:
        return str(obj.category_id) if obj.category_id else None


class PosCategorySerializer(drf_serializers.Serializer):
    """Minimal category record for the POS category browser."""

    id = drf_serializers.UUIDField()
    name = drf_serializers.CharField()
    products_count = drf_serializers.IntegerField()


class PosCatalogProductsView(APIView):
    """
    GET /api/v1/pos/catalog/products/

    Returns active products for the employee's business.

    Optional query params:
        search=<str>        — filter by name or SKU (min 2 chars)
        category_id=<uuid>  — filter by category (exact match)
        in_stock_only=true  — exclude products with stock_quantity <= 0
        limit=<int>         — max results (default 100, hard-cap 200)

    Response 200
    ------------
    { "results": [<PosProductSerializer>, ...], "count": <int> }
    """

    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def get(self, request) -> Response:
        business = request.business
        search = (request.query_params.get('search') or '').strip()
        category_id_raw = (request.query_params.get('category_id') or '').strip()
        in_stock_only = request.query_params.get('in_stock_only', '').lower() in ('true', '1', 'yes')

        try:
            limit = min(int(request.query_params.get('limit', 100)), 200)
        except (ValueError, TypeError):
            limit = 100

        qs = (
            Product.objects
            .filter(business=business, is_active=True)
            .select_related('category')
            .order_by('name')
        )

        if len(search) >= 2:
            qs = qs.filter(
                Q(name__icontains=search) | Q(sku__icontains=search)
            )

        if category_id_raw:
            try:
                category_uuid = uuid_module.UUID(category_id_raw)
                qs = qs.filter(category_id=category_uuid)
            except ValueError:
                pass  # invalid UUID — ignore filter silently

        products = list(qs[:limit])

        # Apply in_stock_only after fetching so we can use ensure_stock_record.
        # This trades a DB hit per product; acceptable for POS catalog sizes.
        if in_stock_only:
            products = [
                p for p in products
                if float(ensure_stock_record(business, p).quantity) > 0
            ]

        data = PosProductSerializer(products, many=True, context={'business': business}).data

        return Response({'results': data, 'count': len(data)})


class PosCatalogCategoriesView(APIView):
    """
    GET /api/v1/pos/catalog/categories/

    Returns active categories for the employee's business, including the
    count of active products in each category.

    Response 200
    ------------
    { "results": [<PosCategorySerializer>, ...], "count": <int> }
    """

    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def get(self, request) -> Response:
        business = request.business

        categories = (
            ProductCategory.objects
            .filter(business=business, is_active=True)
            .annotate(products_count=Count(
                'products', filter=Q(products__is_active=True)
            ))
            .order_by('name')
        )

        data = PosCategorySerializer(categories, many=True).data
        return Response({'results': data, 'count': len(data)})
