import { useBundles } from '../api';
import { Bundle } from '../types';

interface PlansBundlesProps {
  vertical: 'commercial' | 'restaurant';
  billingPeriod: 'monthly' | 'yearly';
  onChooseBundle: (bundle: Bundle) => void;
}

export function PlansBundles({ vertical, billingPeriod, onChooseBundle }: PlansBundlesProps) {
  const { data: bundles, isLoading } = useBundles(vertical);

  if (isLoading) return <div>Cargando packs...</div>;
  if (!bundles?.length) return <div>No hay packs disponibles para esta vertical.</div>;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {bundles.map((bundle) => {
        const price =
          billingPeriod === 'monthly'
            ? bundle.fixed_price_monthly
            : bundle.fixed_price_yearly ?? (bundle.fixed_price_monthly || 0) * 12;

        return (
          <div
            key={bundle.code}
            className={`border rounded-lg p-6 flex flex-col relative bg-white shadow-sm hover:shadow-md transition-shadow ${
              bundle.is_default_recommended ? 'border-blue-500 ring-1 ring-blue-500' : 'border-gray-200'
            }`}
          >
            {bundle.badge && (
              <span className="absolute top-0 right-0 transform translate-x-2 -translate-y-2 bg-yellow-400 text-xs font-bold px-2 py-1 rounded-full shadow-sm text-black">
                {bundle.badge}
              </span>
            )}
            <h3 className="text-xl font-bold mb-2 text-gray-900">{bundle.name}</h3>
            <p className="text-gray-500 text-sm mb-4">{bundle.description}</p>
            
            <div className="my-4">
               <span className="text-3xl font-bold text-gray-900">
                 ${(price ?? 0) / 100}
               </span>
               <span className="text-gray-500 text-sm"> / {billingPeriod === 'monthly' ? 'mes' : 'año'}</span>
            </div>

            <ul className="space-y-2 mb-6 flex-1">
              {bundle.modules.map((m) => (
                <li key={m.code} className="flex items-start text-sm text-gray-700">
                  <span className="mr-2 text-green-500">✓</span>
                  {m.name}
                </li>
              ))}
            </ul>

            <button
              onClick={() => onChooseBundle(bundle)}
              className={`w-full py-2 px-4 rounded-md font-medium transition-colors ${
                bundle.is_default_recommended
                  ? 'bg-blue-600 text-white hover:bg-blue-700'
                  : 'bg-gray-100 text-gray-900 hover:bg-gray-200'
              }`}
            >
              Elegir Pack
            </button>
          </div>
        );
      })}
    </div>
  );
}
