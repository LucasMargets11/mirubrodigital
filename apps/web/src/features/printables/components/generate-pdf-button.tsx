'use client';

import { Button } from '@/components/ui/button';

type GeneratePdfButtonProps = {
  isLoading: boolean;
  disabled?: boolean;
  onClick: () => void;
};

export function GeneratePdfButton({ isLoading, disabled, onClick }: GeneratePdfButtonProps) {
  return (
    <Button
      type="button"
      onClick={onClick}
      disabled={isLoading || disabled}
      className="w-full"
    >
      {isLoading ? 'Generando PDF…' : 'Generar PDF e imprimir'}
    </Button>
  );
}
