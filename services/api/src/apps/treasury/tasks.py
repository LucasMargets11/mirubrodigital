"""
treasury/tasks.py — Celery tasks for document processing pipeline.

Sprint 5: Full pipeline with adapter-based extractors, normalizer,
idempotency, attempt tracking, structured error traces, and
processed_with_warnings support.

process_expense_document(document_id)
  → Transitions: uploaded/queued → processing → processed/processed_with_warnings/failed
  → Uses extractors package (QR-first / OCR-fallback)
  → Normalizes via normalizer.normalize_extraction()
  → Persists raw_extraction, normalized_data, error_trace, pipeline_version, processing_attempts
"""
from __future__ import annotations

import logging
import traceback

from celery import shared_task
from django.db import transaction as db_transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


PIPELINE_VERSION = '5.0'


@shared_task(
    bind=True,
    name='treasury.process_expense_document',
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def process_expense_document(self, document_id: int):
    """
    Process a single ExpenseDocument: QR-first, OCR-fallback extraction + normalization.

    Idempotency: uses select_for_update inside atomic block to prevent
    double-processing of the same document from concurrent task dispatches.

    State transitions:
        uploaded/queued → processing → processed | processed_with_warnings | failed
    """
    from apps.treasury.models import ExpenseDocument

    # ── Step 0: acquire lock + idempotency guard ──────────────────
    try:
        with db_transaction.atomic():
            doc = (
                ExpenseDocument.objects
                .select_for_update(skip_locked=True)
                .get(pk=document_id)
            )

            processable_states = {
                ExpenseDocument.Status.UPLOADED,
                ExpenseDocument.Status.QUEUED,
            }
            if doc.status not in processable_states:
                logger.warning(
                    'document_pipeline doc=%s skipped — status=%s (expected uploaded/queued)',
                    document_id, doc.status,
                )
                return {
                    'status': 'skipped',
                    'detail': f'Document status is {doc.status}',
                    'document_id': document_id,
                }

            # Transition to processing + bump attempt counter
            doc.status = ExpenseDocument.Status.PROCESSING
            doc.processing_attempts = (doc.processing_attempts or 0) + 1
            doc.processing_errors = None
            doc.error_trace = None
            doc.pipeline_version = PIPELINE_VERSION
            doc.save(update_fields=[
                'status', 'processing_attempts', 'processing_errors',
                'error_trace', 'pipeline_version', 'updated_at',
            ])

    except ExpenseDocument.DoesNotExist:
        logger.error('document_pipeline doc=%s not found — aborting', document_id)
        return {'status': 'error', 'detail': 'Document not found', 'document_id': document_id}

    # ── Step 1: extraction ────────────────────────────────────────
    error_trace: list[dict] = []
    try:
        mime_type = doc.mime_type

        # Storage-agnostic: read bytes via Django's storage API
        # Works with local filesystem, S3, GCS, Azure Blob, etc.
        with doc.file.open('rb') as f:
            file_data = f.read()

        from apps.treasury.extractors.orchestrator import extract_document

        result = extract_document(file_data, mime_type)

        # Record any extraction-level errors
        for err in result.get('errors', []):
            error_trace.append({
                'step': 'extraction',
                'error': err,
                'timestamp': timezone.now().isoformat(),
            })

    except FileNotFoundError:
        return _fail_document(
            doc, document_id, self,
            step='file_access',
            error_msg='File not found in storage',
            error_trace=error_trace,
        )
    except Exception as exc:
        return _fail_document(
            doc, document_id, self,
            step='extraction',
            error_msg=str(exc),
            error_trace=error_trace,
            exc=exc,
        )

    # ── Step 2: normalization ─────────────────────────────────────
    try:
        from apps.treasury.normalizer import normalize_extraction

        parsed_fields = result.get('normalized_data', {})
        source_priority = result.get('_source_priority', {})
        normalized = normalize_extraction(parsed_fields, source_priority)

    except Exception as exc:
        error_trace.append({
            'step': 'normalization',
            'error': str(exc),
            'timestamp': timezone.now().isoformat(),
        })
        normalized = None
        logger.exception(
            'document_pipeline doc=%s normalization failed: %s', document_id, exc,
        )

    # ── Step 3: determine final status ────────────────────────────
    extraction_source = result.get('extraction_source', 'none')
    has_warnings = bool(error_trace)
    extraction_successful = extraction_source != 'none'

    if extraction_successful and not has_warnings:
        final_status = ExpenseDocument.Status.PROCESSED
    elif extraction_successful and has_warnings:
        final_status = ExpenseDocument.Status.PROCESSED_WITH_WARNINGS
    elif normalized is None:
        final_status = ExpenseDocument.Status.FAILED
    else:
        # No extraction but normalization didn't crash — processed with warnings
        final_status = ExpenseDocument.Status.PROCESSED_WITH_WARNINGS

    # ── Step 4: persist results ───────────────────────────────────
    now = timezone.now()
    doc.raw_extraction = result.get('raw_extraction', {})
    doc.normalized_data = normalized
    doc.extraction_source = extraction_source
    doc.processing_errors = [e['error'] for e in error_trace] if error_trace else None
    doc.error_trace = error_trace if error_trace else None
    doc.processed_at = now
    doc.status = final_status
    doc.pipeline_version = PIPELINE_VERSION
    doc.save(update_fields=[
        'raw_extraction', 'normalized_data', 'extraction_source',
        'processing_errors', 'error_trace', 'processed_at',
        'status', 'pipeline_version', 'updated_at',
    ])

    # ── Step 5: observability log ─────────────────────────────────
    logger.info(
        'document_pipeline doc=%s status=%s source=%s attempts=%d '
        'warnings=%d confidence=%s pipeline=%s',
        document_id,
        final_status,
        extraction_source,
        doc.processing_attempts,
        len(error_trace),
        normalized.get('confidence', 'n/a') if normalized else 'n/a',
        PIPELINE_VERSION,
    )

    # ── Step 6: trigger fiscal validation (Sprint 4) ──────────────
    if final_status in (
        ExpenseDocument.Status.PROCESSED,
        ExpenseDocument.Status.PROCESSED_WITH_WARNINGS,
    ):
        _trigger_fiscal_validation(doc)

    return {
        'status': final_status,
        'extraction_source': extraction_source,
        'document_id': document_id,
        'processing_attempts': doc.processing_attempts,
        'warnings': len(error_trace),
    }


def _fail_document(
    doc,
    document_id: int,
    task,
    *,
    step: str,
    error_msg: str,
    error_trace: list[dict],
    exc: Exception | None = None,
) -> dict:
    """Persist failure state and decide whether to retry."""
    error_trace.append({
        'step': step,
        'error': error_msg,
        'traceback': traceback.format_exc() if exc else None,
        'timestamp': timezone.now().isoformat(),
    })

    doc.status = doc.Status.FAILED
    doc.processing_errors = [error_msg]
    doc.error_trace = error_trace
    doc.processed_at = timezone.now()
    doc.pipeline_version = PIPELINE_VERSION
    doc.save(update_fields=[
        'status', 'processing_errors', 'error_trace',
        'processed_at', 'pipeline_version', 'updated_at',
    ])

    logger.error(
        'document_pipeline doc=%s FAILED at step=%s attempts=%d error=%s',
        document_id, step, doc.processing_attempts, error_msg,
    )

    # Retry transient errors if attempts remain
    if exc and task.request.retries < task.max_retries:
        raise task.retry(exc=exc)

    return {
        'status': 'failed',
        'detail': error_msg,
        'document_id': document_id,
        'step': step,
    }


def _trigger_fiscal_validation(doc):
    """
    Post-processing hook: re-evaluate the associated fiscal profile if one exists.

    This is a soft dependency on the tax_backup app (Sprint 4).
    If tax_backup is not installed or not configured, this is a no-op.
    Runtime errors inside fiscal validation are logged but never propagate
    to the document processing pipeline.
    """
    from django.apps import apps

    if not apps.is_installed('apps.tax_backup'):
        return

    try:
        from apps.tax_backup.models import ExpenseFiscalProfile
        from apps.tax_backup.fiscal_validation import apply_fiscal_validation
    except ImportError:
        logger.debug(
            'document_pipeline fiscal_validation skipped — tax_backup module not available',
        )
        return

    try:
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
                'document_pipeline fiscal_validation triggered profile=%s doc=%s',
                profile.pk, doc.pk,
            )
    except Exception as exc:
        logger.warning(
            'document_pipeline fiscal_validation runtime error doc=%s: %s',
            doc.pk, exc,
            exc_info=True,
        )
