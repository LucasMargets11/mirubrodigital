import { useState, useEffect } from 'react';
import { useModules, useQuote } from '../api';
import { BillingVertical, QuoteResponse } from '../types';

interface PlansBuilderWizardProps {
  vertical: BillingVertical;
  billingPeriod: 'monthly' | 'yearly';
  onSubscribe: (selectedModules: string[], quote: QuoteResponse) => void;
  onCancel: () => void;
}

export function PlansBuilderWizard({ vertical, billingPeriod, onSubscribe, onCancel }: PlansBuilderWizardProps) {
  const { data: modules, isLoading } = useModules(vertical);
  const quoteMutation = useQuote();

  const [selectedCodes, setSelectedCodes] = useState<string[]>([]);
  const [quote, setQuote] = useState<QuoteResponse | null>(null);

  // Initialize cores
  useEffect(() => {
    if (modules) {
      const cores = modules.filter(m => m.is_core).map(m => m.code);
      setSelectedCodes(prev => Array.from(new Set([...prev, ...cores])));
    }
  }, [modules]);

  const handleToggleModule = (code: string) => {
    setSelectedCodes(prev =>
      prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]
    );
    setQuote(null);
  };

  const handleCalculate = () => {
    quoteMutation.mutate({
      vertical,
      billingPeriod,
      plan_type: 'custom',
      selected_module_codes: selectedCodes
    }, {
      onSuccess: (data) => setQuote(data)
    });
  };

  const isSelected = (code: string) => selectedCodes.includes(code);

  if (isLoading) return <div>Cargando módulos...</div>;

  return (
    <div className="bg-white p-6 rounded-lg max-w-4xl mx-auto shadow-lg">
      <div className="flex justify-between items-center mb-6 border-b pb-4">
        <h2 className="text-2xl font-bold text-gray-900">Armá tu plan a medida</h2>
        <button onClick={onCancel} className="text-gray-500 hover:text-gray-700">Cerrar</button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8 max-h-[60vh] overflow-y-auto">
        {modules?.map(m => (
          <div
            key={m.code}
            className={`border p-4 rounded-lg cursor-pointer transition-colors ${isSelected(m.code) ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'}`}
            onClick={() => !m.is_core && handleToggleModule(m.code)}
          >
            <div className="flex justify-between mb-2 items-start">
              <h4 className="font-semibold text-gray-900">{m.name}</h4>
              <input
                type="checkbox"
                checked={isSelected(m.code)}
                readOnly
                disabled={m.is_core}
                className="mt-1"
              />
            </div>
            <p className="text-xs text-gray-500 mb-2 min-h-[2.5em]">{m.description}</p>
            <div className="flex justify-between items-end">
              <div className="font-mono text-sm font-bold text-gray-700">
                ${((billingPeriod === 'monthly' ? m.price_monthly : (m.price_yearly || m.price_monthly * 12)) / 100).toFixed(2)}
              </div>
              {m.is_core && <span className="text-xs text-blue-600 font-bold bg-blue-100 px-2 py-0.5 rounded">Incluido</span>}
            </div>
          </div>
        ))}
      </div>

      <div className="flex justify-end space-x-4 items-center border-t pt-4">
        <button
          onClick={handleCalculate}
          disabled={quoteMutation.isPending}
          className="px-4 py-2 bg-gray-100 rounded hover:bg-gray-200 text-gray-900 font-medium"
        >
          {quoteMutation.isPending ? 'Calculando...' : 'Calcular Precio'}
        </button>
      </div>

      {quote && (
        <div className="mt-6 border-t pt-6 bg-gray-50 -mx-6 -mb-6 p-6 rounded-b-lg">
          <h3 className="text-xl font-bold mb-4 text-gray-900">Resumen</h3>
          {quote.suggestion && (
            <div className="bg-blue-50 border border-blue-200 p-4 rounded mb-4">
              <p className="font-bold text-blue-800">¡Ahorrá con un Pack!</p>
              <p className="text-sm text-blue-700 mt-1">
                Tu selección coincide con el <strong>{quote.suggestion.bundle_name}</strong>.
                Si cambiás, pagás <strong>${(quote.suggestion.bundle_total / 100).toFixed(2)}</strong> y ahorrás <strong>${(quote.suggestion.savings_amount / 100).toFixed(2)}</strong> ({quote.suggestion.savings_percent}%).
              </p>
              <button
                onClick={() => onSubscribe([], quote)} // Logic to switch to bundle? Ideally logic is in parent or handled here by calling diff prop
                className="text-xs text-white bg-blue-600 px-3 py-1 rounded mt-2 hover:bg-blue-700"
              >
                Mejor cambiar al Pack
              </button>
            </div>
          )}

          <div className="flex justify-between items-center mt-4">
            <div className="text-sm text-gray-600">
              {quote.modules.length} módulos seleccionados
            </div>
            <div className="text-right text-3xl font-bold text-gray-900">
              ${(quote.total / 100).toFixed(2)}
            </div>
          </div>

          <div className="flex justify-end mt-6">
            <button
              onClick={() => onSubscribe(selectedCodes, quote)}
              className="px-8 py-3 bg-green-600 text-white rounded-md font-bold hover:bg-green-700 shadow-md transform active:scale-95 transition-all"
            >
              Confirmar Suscripción
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
