"use client";

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, Upload, X } from 'lucide-react';

import {
  uploadDocument,
  taxBackupKeys,
  type DocumentType,
} from '@/lib/api/tax-backup';
import { Button } from '@/components/ui/button';
import {
  DOCUMENT_TYPE_OPTIONS,
  MAX_FILE_SIZE,
  ACCEPTED_FILE_TYPES,
  ACCEPTED_MIME_TYPES,
} from './constants';

interface Props {
  profileId: number;
  onUploaded: () => void;
  onCancel: () => void;
}

export function DocumentUpload({ profileId, onUploaded, onCancel }: Props) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState<DocumentType>('factura');
  const [isFiscal, setIsFiscal] = useState(true);
  const [issuerName, setIssuerName] = useState('');
  const [issuerTaxId, setIssuerTaxId] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [issueDate, setIssueDate] = useState('');
  const [total, setTotal] = useState('');
  const [fileError, setFileError] = useState('');

  const mutation = useMutation({
    mutationFn: (formData: FormData) => uploadDocument(profileId, formData),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: taxBackupKeys.profile(profileId),
      });
      queryClient.invalidateQueries({ queryKey: taxBackupKeys.summary() });
      onUploaded();
    },
  });

  function validateFile(f: File): string {
    if (f.size > MAX_FILE_SIZE) return 'El archivo no puede superar 10 MB';
    if (!ACCEPTED_MIME_TYPES.includes(f.type))
      return 'Solo se aceptan archivos PDF, JPG, PNG o WEBP';
    return '';
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    if (selected) {
      const err = validateFile(selected);
      setFileError(err);
      setFile(err ? null : selected);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;

    const fd = new FormData();
    fd.append('file', file);
    fd.append('document_type', docType);
    fd.append('is_fiscal_document', String(isFiscal));
    if (issuerName) fd.append('issuer_name', issuerName);
    if (issuerTaxId) fd.append('issuer_tax_id', issuerTaxId);
    if (invoiceNumber) fd.append('invoice_number', invoiceNumber);
    if (issueDate) fd.append('issue_date', issueDate);
    if (total) fd.append('total', total);

    mutation.mutate(fd);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3 p-4 bg-slate-50 rounded-xl border border-slate-200">
      {/* File input */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-1">
          Archivo
        </label>
        {file ? (
          <div className="flex items-center gap-2 text-sm text-slate-700 bg-white p-2 rounded-md border border-slate-200">
            <span className="truncate flex-1">{file.name}</span>
            <button
              type="button"
              onClick={() => setFile(null)}
              className="text-slate-400 hover:text-slate-600"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <label className="flex flex-col items-center justify-center gap-2 p-6 border-2 border-dashed border-slate-300 rounded-lg cursor-pointer hover:border-slate-400 transition-colors">
            <Upload className="h-6 w-6 text-slate-400" />
            <span className="text-sm text-slate-500">
              Arrastrá un archivo o hacé click
            </span>
            <span className="text-xs text-slate-400">
              PDF, JPG, PNG o WEBP — máx. 10 MB
            </span>
            <input
              type="file"
              accept={ACCEPTED_FILE_TYPES}
              onChange={handleFileChange}
              className="hidden"
            />
          </label>
        )}
        {fileError && (
          <p className="text-xs text-rose-600 mt-1">{fileError}</p>
        )}
      </div>

      {/* Fields row */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Tipo de comprobante
          </label>
          <select
            value={docType}
            onChange={(e) => setDocType(e.target.value as DocumentType)}
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          >
            {DOCUMENT_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Nro comprobante
          </label>
          <input
            type="text"
            value={invoiceNumber}
            onChange={(e) => setInvoiceNumber(e.target.value)}
            placeholder="0001-00045234"
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Nombre emisor
          </label>
          <input
            type="text"
            value={issuerName}
            onChange={(e) => setIssuerName(e.target.value)}
            placeholder="Ej. Fibertel SA"
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            CUIT emisor
          </label>
          <input
            type="text"
            value={issuerTaxId}
            onChange={(e) => setIssuerTaxId(e.target.value)}
            placeholder="30-12345678-9"
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Fecha emisión
          </label>
          <input
            type="date"
            value={issueDate}
            onChange={(e) => setIssueDate(e.target.value)}
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Total
          </label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={total}
            onChange={(e) => setTotal(e.target.value)}
            className="block w-full rounded-md border border-slate-300 p-2 text-sm"
          />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={isFiscal}
          onChange={(e) => setIsFiscal(e.target.checked)}
          className="rounded border-slate-300"
        />
        Es comprobante fiscal
      </label>

      {mutation.error && (
        <p className="text-xs text-rose-600">
          Error al subir: {(mutation.error as Error).message}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancelar
        </Button>
        <Button type="submit" size="sm" disabled={!file || mutation.isPending}>
          {mutation.isPending && (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          )}
          Adjuntar
        </Button>
      </div>
    </form>
  );
}
