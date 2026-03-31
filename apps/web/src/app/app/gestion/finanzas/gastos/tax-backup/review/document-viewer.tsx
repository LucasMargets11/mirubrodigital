'use client';

import { useState, useCallback } from 'react';
import {
  FileText,
  Download,
  Replace,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  Upload,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getFileType } from './view-models';

interface DocumentViewerProps {
  fileUrl: string | null;
  fileName?: string;
  canManage: boolean;
  onReplace?: () => void;
  className?: string;
}

export function DocumentViewer({
  fileUrl,
  fileName,
  canManage,
  onReplace,
  className,
}: DocumentViewerProps) {
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const fileType = getFileType(fileUrl);

  const handleZoomIn = useCallback(() => setZoom((z) => Math.min(z + 25, 300)), []);
  const handleZoomOut = useCallback(() => setZoom((z) => Math.max(z - 25, 25)), []);
  const handleRotate = useCallback(() => setRotation((r) => (r + 90) % 360), []);
  const handleResetView = useCallback(() => {
    setZoom(100);
    setRotation(0);
  }, []);

  // No file placeholder
  if (!fileUrl) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-200 bg-slate-50/50 p-8 text-center min-h-[300px]',
          className,
        )}
        role="region"
        aria-label="Visor de comprobante"
      >
        <div className="p-4 bg-white rounded-full shadow-sm mb-4">
          <FileText className="h-10 w-10 text-slate-300" aria-hidden="true" />
        </div>
        <p className="text-base font-semibold text-slate-600">
          Sin comprobante adjunto
        </p>
        <p className="text-sm text-slate-400 mt-1 max-w-xs">
          Subí una factura, recibo o ticket para respaldar este gasto.
        </p>
        {canManage && onReplace && (
          <Button
            onClick={onReplace}
            className="mt-4 gap-2 rounded-full"
            size="sm"
          >
            <Upload className="h-4 w-4" />
            Subir comprobante
          </Button>
        )}
      </div>
    );
  }

  const toolbarId = 'document-viewer-toolbar';

  return (
    <div
      className={cn(
        'flex flex-col rounded-xl border border-slate-200 bg-white overflow-hidden',
        isFullscreen && 'fixed inset-0 z-50 rounded-none',
        className,
      )}
      role="region"
      aria-label="Visor de comprobante"
    >
      {/* Toolbar */}
      <div
        id={toolbarId}
        className="flex items-center justify-between gap-2 px-3 py-2 border-b border-slate-100 bg-slate-50/80"
        role="toolbar"
        aria-label="Controles del visor"
      >
        <div className="flex items-center gap-1">
          <button
            onClick={handleZoomOut}
            className="p-1.5 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors disabled:opacity-40"
            aria-label="Reducir zoom"
            disabled={zoom <= 25}
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <span className="text-xs font-medium text-slate-500 min-w-[3rem] text-center tabular-nums">
            {zoom}%
          </span>
          <button
            onClick={handleZoomIn}
            className="p-1.5 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors disabled:opacity-40"
            aria-label="Ampliar zoom"
            disabled={zoom >= 300}
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          {fileType === 'image' && (
            <button
              onClick={handleRotate}
              className="p-1.5 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              aria-label="Rotar imagen"
            >
              <RotateCcw className="h-4 w-4" />
            </button>
          )}
          {(zoom !== 100 || rotation !== 0) && (
            <button
              onClick={handleResetView}
              className="px-2 py-1 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-md transition-colors"
            >
              Resetear
            </button>
          )}
        </div>

        <div className="flex items-center gap-1">
          {fileUrl && (
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-md transition-colors"
              aria-label="Descargar comprobante"
            >
              <Download className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Descargar</span>
            </a>
          )}
          {canManage && onReplace && (
            <button
              onClick={onReplace}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-md transition-colors"
              aria-label="Reemplazar comprobante"
            >
              <Replace className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Reemplazar</span>
            </button>
          )}
          <button
            onClick={() => setIsFullscreen((f) => !f)}
            className="p-1.5 rounded-md text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors"
            aria-label={isFullscreen ? 'Salir de pantalla completa' : 'Pantalla completa'}
          >
            <Maximize2 className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Content area — no inner scroll in normal mode; fullscreen gets its own */}
      <div
        className={cn(
          'bg-slate-100/50 flex items-center justify-center',
          isFullscreen
            ? 'flex-1 h-full overflow-auto'
            : 'min-h-[300px] overflow-hidden',
        )}
      >
        {fileType === 'pdf' ? (
          <iframe
            src={`${fileUrl}#toolbar=0`}
            title={fileName || 'Comprobante PDF'}
            className="w-full h-full min-h-[300px]"
            style={{
              transform: `scale(${zoom / 100})`,
              transformOrigin: 'top center',
            }}
          />
        ) : fileType === 'image' ? (
          <div className="p-4 flex items-center justify-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={fileUrl}
              alt={fileName || 'Comprobante'}
              className="max-w-full h-auto shadow-lg rounded-md transition-transform duration-200"
              style={{
                transform: `scale(${zoom / 100}) rotate(${rotation}deg)`,
                transformOrigin: 'center center',
              }}
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center p-8 text-center">
            <FileText className="h-12 w-12 text-slate-300 mb-3" aria-hidden="true" />
            <p className="text-sm font-medium text-slate-500">
              No se puede previsualizar este archivo
            </p>
            <a
              href={fileUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-2 text-sm text-indigo-600 hover:text-indigo-700 font-medium"
            >
              Abrir en nueva pestaña
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
