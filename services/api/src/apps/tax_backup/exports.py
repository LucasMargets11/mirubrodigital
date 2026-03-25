"""
Respaldo Impositivo — Export helpers (CSV, ZIP, filename sanitization).

Decisión técnica #2: Sanitización de nombres de archivo en ZIP
 - Se eliminan path separators y caracteres peligrosos.
 - Se trunca a 200 chars.
 - Si hay colisiones, se agrega sufijo incremental (_1, _2, ...).
 - Se impiden paths inseguros (no relative paths, no absolute paths).

Decisión técnica #4: CSV y ZIP reusan ``build_period_queryset()`` de filters.py.
"""
from __future__ import annotations

import csv
import io
import os
import re
import zipfile
from typing import Generator

from django.db.models import QuerySet

from .models import ExpenseFiscalProfile, FiscalDocument

# ── Límites ──────────────────────────────────────────────────────────────
MAX_ZIP_BYTES = 50 * 1024 * 1024   # 50 MB
MAX_FILES_IN_ZIP = 500


# ── Filename sanitization ────────────────────────────────────────────────

# Pattern to strip anything not alphanumeric, dash, underscore, dot, space
_UNSAFE_CHARS = re.compile(r'[^\w\-. ]', re.ASCII)

def sanitize_filename(name: str) -> str:
    """
    Produce un nombre de archivo seguro:
    1. Extrae solo el basename (sin path).
    2. Elimina caracteres no seguros.
    3. Reemplaza espacios múltiples.
    4. Trunca a 200 chars.
    5. Si queda vacío, usa 'documento'.
    """
    # Strip path components — handles both / and \ (Linux + Windows)
    name = name.replace('\\', '/') 
    name = os.path.basename(name)
    # Remove unsafe
    name = _UNSAFE_CHARS.sub('_', name)
    # Collapse repeated underscores/spaces
    name = re.sub(r'[_ ]{2,}', '_', name).strip('_. ')
    # Truncate
    name = name[:200]
    return name or 'documento'


def deduplicate_filename(name: str, seen: dict[str, int]) -> str:
    """
    Si ``name`` ya apareció, agrega sufijo incremental: ``name_1.ext``.
    ``seen`` se modifica in-place (acumula contadores).
    """
    if name not in seen:
        seen[name] = 0
        return name

    seen[name] += 1
    base, dot, ext = name.rpartition('.')
    if not dot:
        return f'{name}_{seen[name]}'
    return f'{base}_{seen[name]}.{ext}'


# ── CSV generation ───────────────────────────────────────────────────────

CSV_HEADERS = [
    'ID', 'Gasto', 'Monto', 'Fecha vencimiento', 'Tipo asignación',
    'Estado fiscal', 'Neto', 'IVA', 'Bien de uso', 'Docs adjuntos',
    'Motivo revisión', 'Creado',
]


def generate_csv_rows(qs: QuerySet[ExpenseFiscalProfile]) -> Generator[str, None, None]:
    """
    Genera filas CSV a partir de un queryset de perfiles fiscales.
    Usa un StringIO buffer para proper CSV escaping.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header
    writer.writerow(CSV_HEADERS)
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate(0)

    for profile in qs.prefetch_related('documents').iterator(chunk_size=500):
        writer.writerow([
            profile.id,
            profile.source_name or '',
            str(profile.source_amount) if profile.source_amount else '',
            str(profile.source_due_date) if profile.source_due_date else '',
            profile.get_allocation_type_display(),
            profile.get_tax_status_display(),
            str(profile.amount_net or ''),
            str(profile.amount_vat or ''),
            'Sí' if profile.is_capital_asset else 'No',
            profile.documents.count(),
            profile.review_reason or '',
            profile.created_at.strftime('%Y-%m-%d %H:%M'),
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)


# ── ZIP generation ───────────────────────────────────────────────────────

def build_zip_buffer(qs: QuerySet[ExpenseFiscalProfile]) -> tuple[io.BytesIO, int]:
    """
    Genera un ZIP en memoria con los documentos fiscales de los perfiles.

    Returns
    -------
    (buffer, file_count) — BytesIO listo para enviar, y cantidad de archivos.

    Raises
    ------
    ValueError si se excede MAX_ZIP_BYTES o MAX_FILES_IN_ZIP.
    """
    buf = io.BytesIO()
    file_count = 0
    total_bytes = 0
    seen_names: dict[str, int] = {}

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        profiles = qs.prefetch_related('documents')
        for profile in profiles.iterator(chunk_size=100):
            source_label = sanitize_filename(
                profile.source_name or f'perfil_{profile.id}'
            )
            folder = f'{profile.id}_{source_label}'

            for doc in profile.documents.all():
                if not doc.file:
                    continue

                file_count += 1
                if file_count > MAX_FILES_IN_ZIP:
                    raise ValueError(
                        f'El ZIP excede el límite de {MAX_FILES_IN_ZIP} archivos.'
                    )

                # Read file content
                try:
                    doc.file.open('rb')
                    content = doc.file.read()
                    doc.file.close()
                except Exception:
                    continue

                total_bytes += len(content)
                if total_bytes > MAX_ZIP_BYTES:
                    raise ValueError(
                        f'El ZIP excede el límite de {MAX_ZIP_BYTES // (1024*1024)} MB.'
                    )

                # Sanitize and deduplicate filename
                original_name = sanitize_filename(os.path.basename(doc.file.name))
                safe_name = deduplicate_filename(original_name, seen_names)

                # Path inside ZIP: folder/filename (no leading slash, no ..)
                arcname = f'{folder}/{safe_name}'
                zf.writestr(arcname, content)

    buf.seek(0)
    return buf, file_count
