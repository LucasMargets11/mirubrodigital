"""
customers/pos_views.py — POS operative endpoints for customer search and creation.

Routes (prefixed with /api/v1/pos/customers/):
  GET  /  — search customers for the employee's business (min 2 chars)
  POST /  — create a minimal customer record

Auth: EmployeeTokenAuthentication + PinChangeNotRequired
Capability: none — any authenticated, pin-cleared employee can search or create customers
"""
from __future__ import annotations

from django.db.models import Q
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import EmployeeTokenAuthentication
from apps.accounts.permissions import EmployeeIsAuthenticated, PinChangeNotRequired

from .models import Customer


# ── Serializers ───────────────────────────────────────────────────────────────


class PosCustomerSerializer(drf_serializers.ModelSerializer):
    """Minimal customer representation for POS sale creation."""

    class Meta:
        model = Customer
        fields = ['id', 'name', 'doc_type', 'doc_number', 'email', 'phone']
        read_only_fields = ['id']


class PosCustomerCreateSerializer(drf_serializers.Serializer):
    """Input serializer for creating a customer from the POS terminal."""

    name = drf_serializers.CharField(max_length=255)
    phone = drf_serializers.CharField(max_length=64, required=False, allow_blank=True, default='')
    email = drf_serializers.EmailField(required=False, allow_blank=True, default='')
    doc_type = drf_serializers.ChoiceField(
        choices=['dni', 'cuit', 'passport', 'other'],
        required=False,
        allow_blank=True,
        default='',
    )
    doc_number = drf_serializers.CharField(max_length=64, required=False, allow_blank=True, default='')

    def validate_name(self, value: str) -> str:
        if not value.strip():
            raise drf_serializers.ValidationError('El nombre no puede estar vacío.')
        return value.strip()


# ── View ──────────────────────────────────────────────────────────────────────


class PosCustomersView(APIView):
    """
    GET  /api/v1/pos/customers/?search=<str>  — search active customers
    POST /api/v1/pos/customers/               — create a customer

    GET query params:
        search=<str>  — filter by name, doc_number, email or phone (min 2 chars)
        limit=<int>   — max results (default 50, hard-cap 100)

    POST body:
        {
            "name": "...",           // required
            "phone": "...",          // optional
            "email": "...",          // optional
            "doc_type": "dni|...",   // optional
            "doc_number": "..."      // optional
        }

    Response 200 (GET):
        { "results": [<PosCustomerSerializer>, ...], "count": <int> }

    Response 201 (POST):
        <PosCustomerSerializer>

    Errors:
        400 → validation (name empty, email invalid, etc.)
        401 → token invalid/expired
        403 → must_change_pin
    """

    authentication_classes = [EmployeeTokenAuthentication]
    permission_classes = [EmployeeIsAuthenticated, PinChangeNotRequired]

    def get(self, request) -> Response:
        business = request.business
        search = (request.query_params.get('search') or '').strip()

        try:
            limit = min(int(request.query_params.get('limit', 50)), 100)
        except (ValueError, TypeError):
            limit = 50

        if len(search) < 2:
            return Response({'results': [], 'count': 0})

        qs = (
            Customer.objects
            .filter(business=business, is_active=True)
            .filter(
                Q(name__icontains=search)
                | Q(doc_number__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
            )
            .order_by('name')[:limit]
        )

        data = PosCustomerSerializer(qs, many=True).data
        return Response({'results': data, 'count': len(data)})

    def post(self, request) -> Response:
        serializer = PosCustomerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        customer = Customer.objects.create(
            business=request.business,
            name=serializer.validated_data['name'],
            phone=serializer.validated_data.get('phone', ''),
            email=serializer.validated_data.get('email', ''),
            doc_type=serializer.validated_data.get('doc_type', ''),
            doc_number=serializer.validated_data.get('doc_number', ''),
        )

        return Response(
            PosCustomerSerializer(customer).data,
            status=status.HTTP_201_CREATED,
        )
