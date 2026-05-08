'use client';

import { PageHeader } from '@/components/app/page-header';
import { PrintableForm } from '@/features/printables/components/printable-form';

export function PrintablesClient() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Carteles y Etiquetas"
        description="Creá carteles de productos y promociones con medidas reales, listos para imprimir en hoja A4."
      />
      <PrintableForm />
    </div>
  );
}
