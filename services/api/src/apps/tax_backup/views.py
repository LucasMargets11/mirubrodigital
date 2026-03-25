import logging

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.db.models import Count, Prefetch, Sum, Q
from django.http import FileResponse, StreamingHttpResponse
from django.utils import timezone

from apps.accounts.permissions import HasBusinessMembership, HasEntitlement, HasPermission

from .checklist import evaluate_checklist
from .filters import build_period_queryset, parse_period_params
from .exports import generate_csv_rows, build_zip_buffer
from .fiscal_validation import apply_fiscal_validation
from .models import (
    DuplicateFlag,
    ExpenseFiscalProfile,
    ExpensePaymentDetail,
    FiscalDocument,
    SourceType,
    TaxStatus,
    TaxStatusLog,
)
from .rules import create_duplicate_flags, evaluate_tax_status
from .serializers import (
    DuplicateFlagSerializer,
    ExpenseFiscalProfileListSerializer,
    ExpenseFiscalProfileSerializer,
    ExpensePaymentDetailSerializer,
    FiscalDocumentSerializer,
    TaxStatusLogSerializer,
)

logger = logging.getLogger(__name__)


# ── Paginación ───────────────────────────────────────────────────────────

class TaxBackupPagination(LimitOffsetPagination):
    default_limit = 50
    max_limit = 200


# ── Base ViewSet ─────────────────────────────────────────────────────────

class BaseTaxBackupViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasBusinessMembership, HasEntitlement, HasPermission]
    required_entitlement = 'gestion.tax_backup'
    required_permission = 'view_finance'
    permission_map = {
        'GET': 'view_finance',
        'POST': 'manage_finance',
        'PUT': 'manage_finance',
        'PATCH': 'manage_finance',
        'DELETE': 'manage_finance',
    }

    def get_queryset(self):
        business = getattr(self.request, 'business', None)
        if hasattr(self.queryset.model, 'business'):
            return self.queryset.filter(business=business)
        return self.queryset

    def perform_create(self, serializer):
        business = getattr(self.request, 'business', None)
        serializer.save(business=business)


# ── Helpers ──────────────────────────────────────────────────────────────

def _apply_rules_and_log(profile: ExpenseFiscalProfile, *, trigger: str = '') -> None:
    """Evalúa reglas de tax_status + fiscal_status, actualiza si cambió, y crea TaxStatusLog."""
    # 1. Tax status rules (existing)
    result = evaluate_tax_status(profile)
    old_status = profile.tax_status
    if result.status != old_status:
        profile.tax_status = result.status
        profile.review_reason = result.note if result.status == TaxStatus.NEEDS_REVIEW else None
        profile.save(update_fields=['tax_status', 'review_reason', 'updated_at'])
        TaxStatusLog.objects.create(
            fiscal_profile=profile,
            previous_status=old_status,
            new_status=result.status,
            rule_code=result.rule_code,
            note=result.note,
        )

    # 2. Sprint 4: Fiscal validation (documentary completeness)
    apply_fiscal_validation(profile, trigger=trigger)


# ── Sprint 3: Document extraction integration ───────────────────────────

# AFIP document types → tax_backup DocumentType mapping
_AFIP_TO_DOC_TYPE = {
    'Factura A': 'factura', 'Factura B': 'factura', 'Factura C': 'factura',
    'Factura M': 'factura',
    'Factura de Crédito Electrónica A': 'factura',
    'Factura de Crédito Electrónica B': 'factura',
    'Factura de Crédito Electrónica C': 'factura',
    'Nota de Crédito A': 'nota_credito', 'Nota de Crédito B': 'nota_credito',
    'Nota de Crédito C': 'nota_credito',
    'Nota de Débito A': 'nota_debito', 'Nota de Débito B': 'nota_debito',
    'Nota de Débito C': 'nota_debito',
    'Recibo': 'recibo', 'Ticket': 'ticket',
}

_FISCAL_DOC_TYPES = {
    'Factura A', 'Factura B', 'Factura C', 'Factura M',
    'Factura de Crédito Electrónica A',
    'Factura de Crédito Electrónica B',
    'Factura de Crédito Electrónica C',
    'Nota de Crédito A', 'Nota de Crédito B', 'Nota de Crédito C',
    'Nota de Débito A', 'Nota de Débito B', 'Nota de Débito C',
}


def _run_document_extraction(doc, request):
    """
    Run Sprint 3 QR/OCR extraction on a FiscalDocument.
    Fills empty fields from extraction results. User-provided data takes precedence.
    """
    from apps.tax_backup.models import ParseStatus

    if not doc.file:
        return

    uploaded_file = request.FILES.get('file')
    mime_type = uploaded_file.content_type if uploaded_file else 'application/pdf'

    try:
        from apps.treasury.extractors import extract_document

        file_path = doc.file.path
        result = extract_document(file_path, mime_type)

        if result['extraction_source'] == 'none':
            doc.parse_status = ParseStatus.FAILED
            doc.save(update_fields=['parse_status'])
            return

        normalized = result.get('normalized_data', {})
        update_fields = ['parse_status']

        # Fill empty fields — user-provided data takes precedence
        if not doc.issuer_tax_id and normalized.get('issuer_tax_id'):
            doc.issuer_tax_id = normalized['issuer_tax_id']
            update_fields.append('issuer_tax_id')

        if not doc.issuer_name and normalized.get('issuer_name'):
            doc.issuer_name = normalized['issuer_name']
            update_fields.append('issuer_name')

        if not doc.invoice_number and normalized.get('document_number'):
            doc.invoice_number = normalized['document_number']
            update_fields.append('invoice_number')

        if not doc.issue_date and normalized.get('issue_date'):
            try:
                from datetime import date as date_type
                doc.issue_date = date_type.fromisoformat(normalized['issue_date'])
                update_fields.append('issue_date')
            except (ValueError, TypeError):
                pass

        if not doc.total and normalized.get('total_amount'):
            try:
                from decimal import Decimal
                doc.total = Decimal(normalized['total_amount'])
                update_fields.append('total')
            except Exception:
                pass

        if normalized.get('currency'):
            doc.currency = normalized['currency']
            update_fields.append('currency')

        if not doc.buyer_tax_id and normalized.get('buyer_tax_id'):
            doc.buyer_tax_id = normalized['buyer_tax_id']
            update_fields.append('buyer_tax_id')

        extracted_type = normalized.get('document_type', '')
        mapped_type = _AFIP_TO_DOC_TYPE.get(extracted_type)
        if mapped_type:
            doc.document_type = mapped_type
            update_fields.append('document_type')

        # Auto-detect fiscal document if extraction found a recognized type
        if extracted_type in _FISCAL_DOC_TYPES:
            doc.is_fiscal_document = True
            update_fields.append('is_fiscal_document')

        # Extract point_of_sale from document_number if available
        doc_num = normalized.get('document_number', '')
        if doc_num and '-' in doc_num and not doc.point_of_sale:
            doc.point_of_sale = doc_num.split('-')[0]
            update_fields.append('point_of_sale')

        doc.parse_status = ParseStatus.PARSED
        doc.save(update_fields=update_fields)

    except Exception as exc:
        logger.exception('FiscalDocument %s extraction failed: %s', doc.pk, exc)
        doc.parse_status = ParseStatus.FAILED
        doc.save(update_fields=['parse_status'])


# ─────────────────────────────────────────────────────────────────────────
# 1. ExpenseFiscalProfile
# ─────────────────────────────────────────────────────────────────────────

class ExpenseFiscalProfileViewSet(BaseTaxBackupViewSet):
    queryset = ExpenseFiscalProfile.objects.select_related(
        'expense', 'fixed_expense_period__fixed_expense',
    ).all()
    serializer_class = ExpenseFiscalProfileSerializer
    pagination_class = TaxBackupPagination
    filter_backends = [filters.SearchFilter]
    search_fields = ['expense__name', 'fixed_expense_period__fixed_expense__name']

    def get_serializer_class(self):
        if self.action == 'list':
            return ExpenseFiscalProfileListSerializer
        return ExpenseFiscalProfileSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ('retrieve', 'list'):
            qs = qs.prefetch_related('documents', 'payment_details', 'status_logs')

        # Filtros por query param
        params = self.request.query_params
        tax_status = params.get('tax_status')
        if tax_status:
            qs = qs.filter(tax_status=tax_status)
        allocation = params.get('allocation_type')
        if allocation:
            qs = qs.filter(allocation_type=allocation)
        source_type = params.get('source_type')
        if source_type and source_type in SourceType.values:
            qs = qs.filter(source_type=source_type)
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        business = getattr(self.request, 'business', None)
        # Derive source_type from the FK provided
        source_type = (
            SourceType.FIXED_EXPENSE_PERIOD
            if serializer.validated_data.get('fixed_expense_period')
            else SourceType.EXPENSE
        )
        profile = serializer.save(
            business=business,
            created_by=self.request.user,
            source_type=source_type,
        )
        # Evaluar reglas iniciales
        _apply_rules_and_log(profile, trigger='create')

    def perform_update(self, serializer):
        profile = serializer.save()
        # Re-evaluar reglas tras edición
        profile.refresh_from_db()
        profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=profile.pk)
        _apply_rules_and_log(profile, trigger='update')

    # ── Nested: Documentos ───────────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'], url_path='documents')
    def documents(self, request, pk=None):
        profile = self.get_object()
        if request.method == 'GET':
            docs = profile.documents.all()
            return Response(FiscalDocumentSerializer(docs, many=True).data)

        self.required_permission = 'manage_finance'
        serializer = FiscalDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        doc = serializer.save(fiscal_profile=profile)

        # Sprint 3 integration: run QR/OCR extraction on the uploaded file
        _run_document_extraction(doc, request)

        # Re-evaluar reglas y buscar duplicados
        profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=profile.pk)
        _apply_rules_and_log(profile, trigger='document_added')
        create_duplicate_flags(profile)
        return Response(FiscalDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'], url_path=r'documents/(?P<doc_id>\d+)')
    def document_detail(self, request, pk=None, doc_id=None):
        self.required_permission = 'manage_finance'
        profile = self.get_object()
        doc = profile.documents.filter(pk=doc_id).first()
        if not doc:
            return Response({'detail': 'Documento no encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        doc.file.delete(save=False)
        doc.delete()
        # Re-evaluar tras borrar documento
        profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=profile.pk)
        _apply_rules_and_log(profile, trigger='document_removed')
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Nested: Pagos ────────────────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'], url_path='payments')
    def payments(self, request, pk=None):
        profile = self.get_object()
        if request.method == 'GET':
            payments = profile.payment_details.all()
            return Response(ExpensePaymentDetailSerializer(payments, many=True).data)

        self.required_permission = 'manage_finance'
        serializer = ExpensePaymentDetailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save(fiscal_profile=profile)
        return Response(ExpensePaymentDetailSerializer(payment).data, status=status.HTTP_201_CREATED)

    # ── Nested: Historial de estado ──────────────────────────────────────

    @action(detail=True, methods=['get'], url_path='status-log')
    def status_log(self, request, pk=None):
        profile = self.get_object()
        logs = profile.status_logs.all()
        return Response(TaxStatusLogSerializer(logs, many=True).data)

    # ── Re-evaluate rules on demand ──────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='re-evaluate')
    def re_evaluate(self, request, pk=None):
        self.required_permission = 'manage_finance'
        profile = self.get_object()
        profile = ExpenseFiscalProfile.objects.prefetch_related('documents').get(pk=profile.pk)
        _apply_rules_and_log(profile, trigger='manual')
        flags = create_duplicate_flags(profile)
        profile.refresh_from_db()
        return Response({
            'tax_status': profile.tax_status,
            'tax_status_display': profile.get_tax_status_display(),
            'duplicates_found': len(flags),
        })

    # ── Dashboard summary ────────────────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        business = getattr(request, 'business', None)
        qs = ExpenseFiscalProfile.objects.filter(business=business)
        by_status = (
            qs.values('tax_status')
            .annotate(count=Count('id'))
            .order_by('tax_status')
        )
        return Response({
            'total': qs.count(),
            'by_status': {row['tax_status']: row['count'] for row in by_status},
        })

    # ── Export CSV ───────────────────────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        """Exporta perfiles fiscales filtrados como CSV streaming."""
        business = getattr(request, 'business', None)
        try:
            params = parse_period_params(request.query_params)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        qs = build_period_queryset(business, **params)

        # Build filename
        parts = ['respaldo_impositivo']
        if params.get('year') and params.get('month'):
            parts.append(f'{params["year"]}_{params["month"]:02d}')
        parts.append('export.csv')
        filename = '_'.join(parts[:2]) + '_' + parts[-1] if len(parts) == 3 else '_'.join(parts)

        response = StreamingHttpResponse(
            generate_csv_rows(qs),
            content_type='text/csv; charset=utf-8',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    # ── Export ZIP ───────────────────────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='export-zip')
    def export_zip(self, request):
        """Exporta documentos fiscales como ZIP con nombres saneados."""
        business = getattr(request, 'business', None)
        try:
            params = parse_period_params(request.query_params)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        qs = build_period_queryset(business, **params)

        try:
            buf, file_count = build_zip_buffer(qs)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if file_count == 0:
            return Response(
                {'detail': 'No hay documentos para exportar en el período seleccionado.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Build filename
        parts = ['respaldo_impositivo']
        if params.get('year') and params.get('month'):
            parts.append(f'{params["year"]}_{params["month"]:02d}')
        filename = '_'.join(parts) + '_documentos.zip'

        response = FileResponse(buf, content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    # ── Monthly report (JSON) ────────────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='monthly-report')
    def monthly_report(self, request):
        """Reporte mensual: resumen numérico por estado, tipo, totales."""
        business = getattr(request, 'business', None)
        try:
            params = parse_period_params(request.query_params)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        qs = build_period_queryset(business, **params)

        total = qs.count()
        by_status = dict(
            qs.values('tax_status')
            .annotate(count=Count('id'))
            .order_by('tax_status')
            .values_list('tax_status', 'count')
        )
        by_allocation = dict(
            qs.values('allocation_type')
            .annotate(count=Count('id'))
            .order_by('allocation_type')
            .values_list('allocation_type', 'count')
        )

        # Aggregates — combine expense + fixed_expense_period amounts
        from django.db.models.functions import Coalesce
        amounts = qs.aggregate(
            total_amount=Sum(
                Coalesce('expense__amount', 'fixed_expense_period__amount'),
            ),
            total_net=Sum('amount_net'),
            total_vat=Sum('amount_vat'),
        )

        # Document counts
        from .models import FiscalDocument
        profile_ids = list(qs.values_list('id', flat=True)[:2000])
        doc_qs = FiscalDocument.objects.filter(fiscal_profile_id__in=profile_ids)
        doc_total = doc_qs.count()
        doc_fiscal = doc_qs.filter(is_fiscal_document=True).count()

        return Response({
            'period': {
                'month': params.get('month'),
                'year': params.get('year'),
            },
            'profiles': {
                'total': total,
                'by_status': by_status,
                'by_allocation': by_allocation,
            },
            'amounts': {
                'total_expense': str(amounts['total_amount'] or 0),
                'total_net': str(amounts['total_net'] or 0),
                'total_vat': str(amounts['total_vat'] or 0),
            },
            'documents': {
                'total': doc_total,
                'fiscal': doc_fiscal,
                'non_fiscal': doc_total - doc_fiscal,
            },
        })


    # ── Checklist operativo mensual ────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='checklist')
    def checklist(self, request):
        """Checklist operativo: 6 reglas que validan si el período está listo."""
        business = getattr(request, 'business', None)
        try:
            params = parse_period_params(request.query_params)
        except ValueError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        qs = build_period_queryset(business, **params)
        result = evaluate_checklist(
            business,
            qs,
            month=params.get('month'),
            year=params.get('year'),
        )
        return Response(result)


# ─────────────────────────────────────────────────────────────────────────
# 2. DuplicateFlag
# ─────────────────────────────────────────────────────────────────────────

class DuplicateFlagViewSet(BaseTaxBackupViewSet):
    queryset = DuplicateFlag.objects.select_related(
        'fiscal_profile__expense',
        'fiscal_profile__fixed_expense_period__fixed_expense',
        'matched_profile__expense',
        'matched_profile__fixed_expense_period__fixed_expense',
    ).all()
    serializer_class = DuplicateFlagSerializer
    pagination_class = TaxBackupPagination
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        business = getattr(self.request, 'business', None)
        qs = DuplicateFlag.objects.filter(
            fiscal_profile__business=business,
        ).select_related(
            'fiscal_profile__expense',
            'fiscal_profile__fixed_expense_period__fixed_expense',
            'matched_profile__expense',
            'matched_profile__fixed_expense_period__fixed_expense',
        )

        dup_status = self.request.query_params.get('status')
        if dup_status:
            qs = qs.filter(status=dup_status)
        return qs.order_by('-created_at')
