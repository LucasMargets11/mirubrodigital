"""
treasury/tasks.py — Celery tasks for document processing pipeline.

Sprint 3: On-demand task dispatched via .delay() from the API (first
on-demand Celery usage in the project).

process_expense_document(document_id)
  → Transitions: uploaded → queued → processing → processed | failed
  → Calls extractors.extract_document() for QR-first / OCR-fallback
  → Persists raw_extraction, normalized_data, extraction_source
"""
from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='treasury.process_expense_document',
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def process_expense_document(self, document_id: int):
    """
    Process a single ExpenseDocument: QR-first, OCR-fallback extraction.

    Called via:
        process_expense_document.delay(document.id)

    State transitions:
        uploaded/queued → processing → processed | failed
    """
    from apps.treasury.models import ExpenseDocument

    try:
        doc = ExpenseDocument.objects.select_for_update().get(pk=document_id)
    except ExpenseDocument.DoesNotExist:
        logger.error('ExpenseDocument %s not found — aborting', document_id)
        return {'status': 'error', 'detail': 'Document not found'}

    # Guard: only process if in a valid pre-processing state (anti re-entry)
    processable_states = {
        ExpenseDocument.Status.UPLOADED,
        ExpenseDocument.Status.QUEUED,
    }
    if doc.status not in processable_states:
        logger.warning(
            'ExpenseDocument %s skipped — status=%s (expected uploaded/queued)',
            document_id, doc.status,
        )
        return {'status': 'skipped', 'detail': f'Document status is {doc.status}'}

    # Transition to processing
    doc.status = ExpenseDocument.Status.PROCESSING
    doc.processing_errors = None
    doc.save(update_fields=['status', 'processing_errors', 'updated_at'])

    try:
        file_path = doc.file.path
        mime_type = doc.mime_type

        from apps.treasury.extractors import extract_document

        result = extract_document(file_path, mime_type)

        # Persist results
        doc.raw_extraction = result['raw_extraction']
        doc.normalized_data = result['normalized_data']
        doc.extraction_source = result['extraction_source']
        doc.processing_errors = result['errors'] if result['errors'] else None
        doc.processed_at = timezone.now()
        doc.status = ExpenseDocument.Status.PROCESSED
        doc.save(update_fields=[
            'raw_extraction', 'normalized_data', 'extraction_source',
            'processing_errors', 'processed_at', 'status', 'updated_at',
        ])

        logger.info(
            'ExpenseDocument %s processed: source=%s, fields=%d',
            document_id,
            result['extraction_source'],
            len(result.get('normalized_data', {})),
        )

        # Sprint 4: Trigger fiscal validation on associated fiscal profile
        _trigger_fiscal_validation(doc)

        return {
            'status': 'processed',
            'extraction_source': result['extraction_source'],
            'document_id': document_id,
        }

    except Exception as exc:
        logger.exception('ExpenseDocument %s processing failed: %s', document_id, exc)

        # Persist failure
        doc.status = ExpenseDocument.Status.FAILED
        doc.processing_errors = [str(exc)]
        doc.processed_at = timezone.now()
        doc.save(update_fields=[
            'status', 'processing_errors', 'processed_at', 'updated_at',
        ])

        # Retry if attempts remain
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)

        return {
            'status': 'failed',
            'detail': str(exc),
            'document_id': document_id,
        }


def _trigger_fiscal_validation(doc):
    """
    Sprint 4: After processing an ExpenseDocument, re-evaluate the
    associated fiscal profile if one exists.
    """
    try:
        from apps.tax_backup.models import ExpenseFiscalProfile
        from apps.tax_backup.fiscal_validation import apply_fiscal_validation

        profile = None
        if doc.expense_id:
            profile = ExpenseFiscalProfile.objects.filter(
                expense_id=doc.expense_id,
            ).prefetch_related('documents').first()
        elif doc.fixed_expense_period_id:
            profile = ExpenseFiscalProfile.objects.filter(
                fixed_expense_period_id=doc.fixed_expense_period_id,
            ).prefetch_related('documents').first()

        if profile:
            apply_fiscal_validation(profile, trigger='document_processed')
            logger.info(
                'Fiscal validation triggered for profile %s after document %s processing',
                profile.pk, doc.pk,
            )
    except Exception as exc:
        logger.warning(
            'Fiscal validation trigger failed for document %s: %s',
            doc.pk, exc,
        )
