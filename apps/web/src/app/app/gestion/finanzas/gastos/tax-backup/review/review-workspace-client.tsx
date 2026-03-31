'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Loader2, AlertCircle, Trash2 } from 'lucide-react';

import {
  getProfile,
  reEvaluateProfile,
  deleteDocument,
  taxBackupKeys,
  type FiscalProfileDetail,
  type FiscalDocument,
} from '@/lib/api/tax-backup';
import { Button } from '@/components/ui/button';
import { DISCLAIMER_TEXT } from '../constants';
import { DocumentUpload } from '../document-upload';
import { PaymentForm } from '../payment-form';

import { ReviewHeader } from './review-header';
import { StatusCard } from './status-card';
import { DocumentViewer } from './document-viewer';
import { ExtractionSummary } from './extraction-summary';
import { ExpenseComparison } from './expense-comparison';
import { CompletionChecklist } from './completion-checklist';
import { RecommendedActions } from './recommended-actions';
import { TechnicalTrace } from './technical-trace';
import { ReviewTimeline } from './review-timeline';
import {
  deriveOperationalStatus,
  buildComparison,
  getRecommendedActions,
  type RecommendedAction,
} from './view-models';

interface Props {
  profileId: number;
  canManage: boolean;
}

export function ReviewWorkspaceClient({ profileId, canManage }: Props) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [showUpload, setShowUpload] = useState(false);
  const [showPayment, setShowPayment] = useState(false);

  const {
    data: profile,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: taxBackupKeys.profile(profileId),
    queryFn: () => getProfile(profileId),
    refetchInterval: (query) => {
      // Auto-refresh while processing
      const p = query.state.data as FiscalProfileDetail | undefined;
      if (p?.documents?.some((d) => d.parse_status === 'pending')) return 3000;
      return false;
    },
  });

  const reEvalMutation = useMutation({
    mutationFn: () => reEvaluateProfile(profileId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taxBackupKeys.profile(profileId) });
      queryClient.invalidateQueries({ queryKey: taxBackupKeys.summary() });
    },
  });

  const deleteDocMutation = useMutation({
    mutationFn: (docId: number) => deleteDocument(profileId, docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taxBackupKeys.profile(profileId) });
      queryClient.invalidateQueries({ queryKey: taxBackupKeys.summary() });
    },
  });

  const handleBack = useCallback(() => {
    router.push('/app/gestion/finanzas/gastos?tab=respaldo' as any);
  }, [router]);

  const handleAction = useCallback(
    (actionType: RecommendedAction['actionType']) => {
      switch (actionType) {
        case 'upload':
        case 'replace':
          setShowUpload(true);
          break;
        case 'payment':
          setShowPayment(true);
          break;
        case 'confirm':
          reEvalMutation.mutate();
          break;
        case 'defer':
          // For now, go back to inbox
          handleBack();
          break;
        case 'edit':
          // Scroll to extraction summary
          document.getElementById('extraction-section')?.scrollIntoView({ behavior: 'smooth' });
          break;
        case 'technical':
          document.getElementById('technical-section')?.scrollIntoView({ behavior: 'smooth' });
          break;
      }
    },
    [reEvalMutation, handleBack],
  );

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
          <p className="text-sm text-slate-500">Cargando comprobante...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (isError || !profile) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-3 text-center">
        <AlertCircle className="h-10 w-10 text-slate-300" />
        <p className="text-base font-medium text-slate-600">
          No se pudo cargar el perfil fiscal
        </p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Reintentar
          </Button>
          <Button variant="outline" size="sm" onClick={handleBack}>
            Volver a Respaldo
          </Button>
        </div>
      </div>
    );
  }

  const p = profile as FiscalProfileDetail;
  const operationalStatus = deriveOperationalStatus(p);
  const hasDocs = (p.documents?.length ?? 0) > 0;
  const primaryDoc: FiscalDocument | null = hasDocs ? p.documents[0] : null;
  const comparisonFields = buildComparison(p, primaryDoc);
  const recommendedActions = getRecommendedActions(p, operationalStatus);

  const handleDownload = primaryDoc?.file
    ? () => window.open(primaryDoc.file, '_blank', 'noopener,noreferrer')
    : undefined;
  const handleReplace = canManage ? () => setShowUpload(true) : undefined;

  return (
    <div className="flex flex-col gap-6">
      {/* Sticky header — sticks inside AppShell's overflow-y-auto main */}
      <ReviewHeader
        profile={p}
        operationalStatus={operationalStatus}
        onBack={handleBack}
        onReplace={handleReplace}
        onDownload={handleDownload}
      />

      {/* Main content */}
      <div className="space-y-6">
        {/* Status card */}
        <StatusCard
          status={operationalStatus}
          nextAction={p.next_recommended_action}
        />

        {/* Upload overlay */}
        {showUpload && canManage && (
          <div className="rounded-xl border border-indigo-200 bg-indigo-50/30 p-5">
            <DocumentUpload
              profileId={profileId}
              onUploaded={() => setShowUpload(false)}
              onCancel={() => setShowUpload(false)}
            />
          </div>
        )}

        {/* Two-column layout: document viewer + analysis */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left column: Document viewer */}
          <div className="space-y-6">
            {hasDocs ? (
              <>
                <DocumentViewer
                  fileUrl={primaryDoc?.file ?? null}
                  fileName={primaryDoc ? `${p.source_name}-comprobante` : undefined}
                  canManage={canManage}
                  onReplace={handleReplace}
                />

                {/* All documents list with delete actions */}
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <h4 className="text-sm font-bold text-slate-800 mb-2">
                    Comprobantes adjuntos ({p.documents.length})
                  </h4>
                  <div className="space-y-2">
                    {p.documents.map((doc, idx) => (
                      <div
                        key={doc.id}
                        className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors"
                      >
                        <a
                          href={doc.file}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-center gap-2 text-sm min-w-0 flex-1"
                        >
                          <span className="font-medium text-slate-700">
                            {doc.document_type === 'factura' ? 'Factura' : doc.document_type}
                            {idx === 0 && (
                              <span className="ml-1.5 text-[10px] font-semibold text-indigo-600 bg-indigo-50 px-1.5 py-0.5 rounded">
                                Principal
                              </span>
                            )}
                          </span>
                          {doc.invoice_number && (
                            <span className="text-slate-500">#{doc.invoice_number}</span>
                          )}
                          {doc.parse_status === 'failed' && doc.processing_error && (
                            <span className="text-[10px] text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200">
                              Error: {doc.processing_error.slice(0, 50)}
                            </span>
                          )}
                        </a>
                        {canManage && (
                          <button
                            onClick={() => deleteDocMutation.mutate(doc.id)}
                            disabled={deleteDocMutation.isPending}
                            className="p-1.5 rounded-md text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors disabled:opacity-40 shrink-0"
                            aria-label="Eliminar comprobante"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <DocumentViewer
                fileUrl={null}
                canManage={canManage}
                onReplace={handleReplace}
              />
            )}
          </div>

          {/* Right column: Analysis */}
          <div className="space-y-6">
            {/* Comparison: gasto vs comprobante */}
            <ExpenseComparison fields={comparisonFields} />

            {/* Extraction summary */}
            <div id="extraction-section">
              <ExtractionSummary document={primaryDoc} />
            </div>

            {/* Completion checklist */}
            <CompletionChecklist items={p.completion_items ?? []} />

            {/* Recommended actions */}
            {canManage && (
              <RecommendedActions
                actions={recommendedActions}
                onAction={handleAction}
              />
            )}

            {/* Payment form */}
            {showPayment && canManage && (
              <div className="rounded-xl border border-indigo-200 bg-indigo-50/30 p-5">
                <PaymentForm
                  profileId={profileId}
                  onAdded={() => setShowPayment(false)}
                  onCancel={() => setShowPayment(false)}
                />
              </div>
            )}

            {/* Timeline */}
            <ReviewTimeline
              logs={p.status_logs ?? []}
              documentCreatedAt={primaryDoc?.created_at}
            />

            {/* Technical trace */}
            <div id="technical-section">
              <TechnicalTrace profile={p} document={primaryDoc} />
            </div>

            {/* Disclaimer */}
            <p className="text-[11px] text-slate-400 leading-snug text-center py-2">
              {DISCLAIMER_TEXT}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
