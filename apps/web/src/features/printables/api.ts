import type { GeneratePrintablePdfPayload } from './types';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

/**
 * Llama al endpoint POST /api/v1/printables/generate-pdf/ y devuelve el Blob del PDF.
 * No usa apiPost porque ese helper parsea JSON; este endpoint devuelve application/pdf.
 */
export async function generatePrintablePdf(
  payload: GeneratePrintablePdfPayload,
): Promise<Blob> {
  const response = await fetch(`${API_URL}/api/v1/printables/generate-pdf/`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    let message = 'No se pudo generar el PDF.';
    try {
      const data = await response.json();
      message = (data as { message?: string; detail?: string })?.message
        ?? (data as { message?: string; detail?: string })?.detail
        ?? message;
    } catch {
      // mantener mensaje default
    }
    throw new Error(message);
  }

  return response.blob();
}

/**
 * Dispara la descarga del blob como archivo.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
