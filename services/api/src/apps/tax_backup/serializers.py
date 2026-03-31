from decimal import Decimal

from rest_framework import serializers

from .models import (
    AllocationType,
    DuplicateFlag,
    EvaluationSource,
    ExpenseFiscalProfile,
    ExpensePaymentDetail,
    FiscalDocument,
    FiscalStatus,
    SourceType,
    TaxStatus,
    TaxStatusLog,
)

# ── Tamaño máximo de archivo: 10 MB ─────────────────────────────────────
MAX_FILE_SIZE = 10 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    'application/pdf',
    'image/jpeg',
    'image/png',
    'image/webp',
}


def _validate_file(value):
    if value.size > MAX_FILE_SIZE:
        raise serializers.ValidationError('El archivo no puede superar 10 MB.')
    ct = getattr(value, 'content_type', '')
    if ct and ct not in ALLOWED_CONTENT_TYPES:
        raise serializers.ValidationError(
            f'Tipo de archivo no permitido ({ct}). Aceptados: PDF, JPEG, PNG, WEBP.'
        )


# ─────────────────────────────────────────────────────────────────────────
# FiscalDocument
# ─────────────────────────────────────────────────────────────────────────

class FiscalDocumentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(validators=[_validate_file])

    class Meta:
        model = FiscalDocument
        fields = '__all__'
        read_only_fields = ('fiscal_profile', 'created_at', 'parse_status', 'processing_error')


class FiscalDocumentListSerializer(serializers.ModelSerializer):
    """Versión ligera para listados — sin datos detallados del comprobante."""
    class Meta:
        model = FiscalDocument
        fields = (
            'id', 'document_type', 'document_subtype', 'issuer_name',
            'issuer_tax_id', 'invoice_number', 'issue_date', 'total',
            'currency', 'is_fiscal_document', 'created_at',
            'parse_status', 'processing_error', 'file',
            'point_of_sale', 'buyer_tax_id', 'buyer_name',
        )


# ─────────────────────────────────────────────────────────────────────────
# ExpensePaymentDetail
# ─────────────────────────────────────────────────────────────────────────

class ExpensePaymentDetailSerializer(serializers.ModelSerializer):
    proof_file = serializers.FileField(required=False, allow_null=True, validators=[_validate_file])

    class Meta:
        model = ExpensePaymentDetail
        fields = '__all__'
        read_only_fields = ('fiscal_profile', 'created_at')


# ─────────────────────────────────────────────────────────────────────────
# TaxStatusLog (read-only)
# ─────────────────────────────────────────────────────────────────────────

class TaxStatusLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxStatusLog
        fields = '__all__'
        read_only_fields = ('id', 'fiscal_profile', 'previous_status', 'new_status', 'rule_code', 'note', 'created_at')


# ─────────────────────────────────────────────────────────────────────────
# ExpenseFiscalProfile
# ─────────────────────────────────────────────────────────────────────────

class ExpenseFiscalProfileSerializer(serializers.ModelSerializer):
    documents = FiscalDocumentListSerializer(many=True, read_only=True)
    payment_details = ExpensePaymentDetailSerializer(many=True, read_only=True)
    status_logs = TaxStatusLogSerializer(many=True, read_only=True)

    # Campos agnósticos de origen — usan las properties del modelo
    source_name = serializers.CharField(read_only=True)
    source_amount = serializers.DecimalField(
        max_digits=19, decimal_places=4, read_only=True,
    )
    source_due_date = serializers.DateField(read_only=True)
    source_type = serializers.CharField(read_only=True)
    source_period_label = serializers.CharField(read_only=True, allow_null=True)
    source_status = serializers.CharField(read_only=True, allow_null=True)

    # Datos legacy del Expense (backwards-compat en API, serán None para fixed_expense_period)
    expense_name = serializers.CharField(source='expense.name', read_only=True, default=None)
    expense_amount = serializers.DecimalField(
        source='expense.amount', max_digits=19, decimal_places=4, read_only=True, default=None,
    )
    expense_status = serializers.CharField(source='expense.status', read_only=True, default=None)
    expense_due_date = serializers.DateField(source='expense.due_date', read_only=True, default=None)

    tax_status_display = serializers.CharField(
        source='get_tax_status_display', read_only=True,
    )
    allocation_type_display = serializers.CharField(
        source='get_allocation_type_display', read_only=True,
    )

    # ── UX enrichment (read-only, computed) ──────────────────────────────
    human_status_title = serializers.SerializerMethodField()
    human_status_description = serializers.SerializerMethodField()
    next_recommended_action = serializers.SerializerMethodField()
    completion_items = serializers.SerializerMethodField()

    # ── Sprint 4: Fiscal validation fields (read-only) ───────────────────
    fiscal_status_display = serializers.CharField(
        source='get_fiscal_status_display', read_only=True,
    )
    fiscal_status_label = serializers.SerializerMethodField()
    missing_fields_labels = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseFiscalProfile
        fields = '__all__'
        read_only_fields = (
            'business', 'tax_status', 'source_type', 'created_by', 'created_at', 'updated_at',
            # Sprint 4: fiscal validation fields are computed by the service
            'fiscal_status', 'review_required', 'missing_fields',
            'validation_issues', 'evaluated_at', 'evaluation_source',
        )

    # ── UX enrichment methods ────────────────────────────────────────────

    _STATUS_HUMAN = {
        TaxStatus.REGISTERED: {
            'title': 'Pendiente de completar',
            'desc': 'Este gasto fue registrado pero todavía no tiene respaldo fiscal completo.',
        },
        TaxStatus.BACKED: {
            'title': 'Respaldo fiscal completo',
            'desc': 'Este gasto tiene toda la documentación fiscal necesaria.',
        },
        TaxStatus.POTENTIALLY_DEDUCTIBLE: {
            'title': 'Deducción parcial posible',
            'desc': 'Es un gasto mixto con comprobante fiscal. Puede deducirse proporcionalmente.',
        },
        TaxStatus.NEEDS_REVIEW: {
            'title': 'Requiere tu atención',
            'desc': 'Se detectaron inconsistencias que necesitan ser corregidas.',
        },
        TaxStatus.NOT_BACKED: {
            'title': 'Sin respaldo fiscal',
            'desc': 'Este gasto no puede ser deducido en su estado actual.',
        },
    }

    _RULE_ACTIONS = {
        'RULE_PERSONAL': 'Si querés deducirlo, cambiá la asignación a Negocio o Mixto.',
        'RULE_NO_DOC': 'Adjuntá un comprobante fiscal (factura, recibo, ticket).',
        'RULE_NO_FISCAL_DOC': 'Los documentos adjuntos no son fiscales. Adjuntá un comprobante fiscal válido.',
        'RULE_CAPITAL_ASSET': 'Consultá con tu contador sobre la amortización de este bien de uso.',
        'RULE_MIXED': 'Definí con tu contador qué porcentaje es deducible.',
        'RULE_AMOUNT_MISMATCH': 'Revisá que el total del comprobante coincida con el monto del gasto.',
        'RULE_NO_BUYER_TAX_ID': 'Pedí un comprobante que incluya tu CUIT/RUT como comprador.',
        'RULE_BACKED': None,
        'RULE_FALLBACK': 'Adjuntá un comprobante fiscal para completar el respaldo.',
    }

    def _get_last_rule_code(self, obj):
        """Extract the rule_code from the latest status log, or re-derive it."""
        cache = getattr(obj, '_prefetched_objects_cache', None) or {}
        logs = list(cache['status_logs']) if 'status_logs' in cache else list(obj.status_logs.order_by('-created_at')[:1])
        if logs:
            return logs[0].rule_code if hasattr(logs[0], 'rule_code') else None
        # Fallback: derive from review_reason or status
        return None

    def get_human_status_title(self, obj):
        info = self._STATUS_HUMAN.get(obj.tax_status)
        return info['title'] if info else obj.get_tax_status_display()

    def get_human_status_description(self, obj):
        info = self._STATUS_HUMAN.get(obj.tax_status)
        return info['desc'] if info else ''

    def get_next_recommended_action(self, obj):
        if obj.tax_status == TaxStatus.BACKED:
            return None
        # Find rule from latest log
        rule_code = self._get_last_rule_code(obj)
        if rule_code and rule_code in self._RULE_ACTIONS:
            return self._RULE_ACTIONS[rule_code]
        # Derive from status
        if obj.tax_status == TaxStatus.NOT_BACKED:
            if obj.allocation_type == AllocationType.PERSONAL:
                return self._RULE_ACTIONS['RULE_PERSONAL']
            return self._RULE_ACTIONS['RULE_NO_DOC']
        if obj.tax_status == TaxStatus.NEEDS_REVIEW:
            return 'Revisá los datos del comprobante y corregí las inconsistencias detectadas.'
        return self._RULE_ACTIONS.get('RULE_FALLBACK')

    def get_completion_items(self, obj):
        """Checklist items for what's complete/missing on this profile."""
        docs = list(
            (getattr(obj, '_prefetched_objects_cache', None) or {}).get('documents', [])
        ) or list(obj.documents.all())
        payments = list(
            (getattr(obj, '_prefetched_objects_cache', None) or {}).get('payment_details', [])
        ) or list(obj.payment_details.all())

        has_docs = len(docs) > 0
        has_fiscal_doc = any(d.is_fiscal_document for d in docs)
        has_payment = len(payments) > 0
        has_buyer_tax_id = any(d.is_fiscal_document and d.buyer_tax_id for d in docs)
        allocation_defined = obj.allocation_type in (
            AllocationType.BUSINESS, AllocationType.MIXED, AllocationType.PERSONAL,
        )
        no_review_needed = obj.tax_status != TaxStatus.NEEDS_REVIEW

        # Amount match check
        amount_matches = True
        if has_fiscal_doc and obj.source_amount is not None:
            fiscal_total = sum(
                (d.total or Decimal('0')) for d in docs if d.is_fiscal_document
            )
            amount_matches = abs(fiscal_total - obj.source_amount) <= Decimal('1')

        items = [
            {
                'key': 'fiscal_doc',
                'label': 'Comprobante fiscal válido',
                'done': has_fiscal_doc,
                'applicable': True,
                'hint': 'Adjuntá una factura, recibo o ticket fiscal' if not has_fiscal_doc else None,
            },
            {
                'key': 'payment',
                'label': 'Pago registrado',
                'done': has_payment,
                'applicable': True,
                'hint': 'Registrá el pago asociado a este gasto' if not has_payment else None,
            },
            {
                'key': 'buyer_tax_id',
                'label': 'CUIT/RUT del comprador',
                'done': has_buyer_tax_id,
                'applicable': has_fiscal_doc,
                'hint': 'El comprobante fiscal debe incluir tu CUIT/RUT' if not has_buyer_tax_id else None,
            },
            {
                'key': 'amount_match',
                'label': 'Monto coincide con comprobante',
                'done': amount_matches,
                'applicable': has_fiscal_doc,
                'hint': 'El total del comprobante difiere del monto del gasto' if not amount_matches else None,
            },
            {
                'key': 'allocation',
                'label': 'Asignación definida',
                'done': allocation_defined,
                'applicable': True,
                'hint': None,
            },
            {
                'key': 'review_resolved',
                'label': 'Observaciones resueltas' if no_review_needed else 'Observaciones pendientes',
                'done': no_review_needed,
                'applicable': True,
                'hint': 'Resolvé las observaciones para avanzar' if not no_review_needed else None,
            },
        ]
        return items

    # ── Sprint 4: Fiscal validation display helpers ──────────────────────

    _FISCAL_STATUS_LABELS = {
        FiscalStatus.SIN_COMPROBANTE: 'Sin comprobante',
        FiscalStatus.INCOMPLETO: 'Datos incompletos',
        FiscalStatus.REQUIERE_REVISION: 'Requiere revisión',
        FiscalStatus.VALIDO_CON_OBSERVACIONES: 'Válido con observaciones',
        FiscalStatus.VALIDO: 'Válido',
    }

    _MISSING_FIELD_LABELS = {
        'document_type': 'Tipo de comprobante',
        'invoice_number': 'Número de comprobante',
        'issuer_tax_id': 'CUIT emisor',
        'issue_date': 'Fecha de emisión',
        'total': 'Total',
        'is_fiscal_document': 'Indicador fiscal',
        'buyer_tax_id': 'CUIT/RUT comprador',
    }

    def get_fiscal_status_label(self, obj):
        return self._FISCAL_STATUS_LABELS.get(obj.fiscal_status, obj.get_fiscal_status_display())

    def get_missing_fields_labels(self, obj):
        if not obj.missing_fields:
            return []
        return [
            {
                'key': f,
                'label': self._MISSING_FIELD_LABELS.get(f, f),
            }
            for f in obj.missing_fields
        ]

    def validate(self, attrs):
        """Impedir crear perfil para un gasto que no pertenece al business."""
        request = self.context.get('request')
        business = getattr(request, 'business', None) if request else None

        expense = attrs.get('expense')
        fep = attrs.get('fixed_expense_period')

        # En PATCH parcial, solo validar si se envían estos campos
        if self.instance is None:
            # CREATE — exigir exactamente un origen
            if expense and fep:
                raise serializers.ValidationError('Solo uno de expense o fixed_expense_period debe estar presente.')
            if not expense and not fep:
                raise serializers.ValidationError('Se requiere expense o fixed_expense_period.')

        if business:
            if expense and expense.business_id != business.id:
                raise serializers.ValidationError({'expense': 'El gasto no pertenece a este negocio.'})
            if fep and fep.fixed_expense.business_id != business.id:
                raise serializers.ValidationError({'fixed_expense_period': 'El período no pertenece a este negocio.'})

        return attrs


class ExpenseFiscalProfileListSerializer(serializers.ModelSerializer):
    """Versión compacta para listados con semáforo."""
    source_name = serializers.CharField(read_only=True)
    source_amount = serializers.DecimalField(
        max_digits=19, decimal_places=4, read_only=True,
    )
    source_due_date = serializers.DateField(read_only=True)
    source_type = serializers.CharField(read_only=True)
    source_period_label = serializers.CharField(read_only=True, allow_null=True)
    source_status = serializers.CharField(read_only=True, allow_null=True)
    tax_status_display = serializers.CharField(
        source='get_tax_status_display', read_only=True,
    )
    fiscal_status_display = serializers.CharField(
        source='get_fiscal_status_display', read_only=True,
    )
    doc_count = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseFiscalProfile
        fields = (
            'id', 'expense', 'fixed_expense_period', 'source_type',
            'source_name', 'source_amount', 'source_due_date',
            'source_period_label', 'source_status',
            'allocation_type', 'tax_status', 'tax_status_display',
            'fiscal_status', 'fiscal_status_display', 'review_required',
            'is_capital_asset', 'doc_count', 'created_at',
        )

    def get_doc_count(self, obj):
        cache = getattr(obj, '_prefetched_objects_cache', None) or {}
        if 'documents' in cache:
            return len(cache['documents'])
        return obj.documents.count()


# ─────────────────────────────────────────────────────────────────────────
# DuplicateFlag
# ─────────────────────────────────────────────────────────────────────────

class DuplicateFlagSerializer(serializers.ModelSerializer):
    fiscal_profile_source_name = serializers.CharField(
        source='fiscal_profile.source_name', read_only=True,
    )
    matched_profile_source_name = serializers.CharField(
        source='matched_profile.source_name', read_only=True,
    )

    class Meta:
        model = DuplicateFlag
        fields = '__all__'
        read_only_fields = (
            'fiscal_profile', 'matched_profile', 'match_type', 'created_at',
        )
