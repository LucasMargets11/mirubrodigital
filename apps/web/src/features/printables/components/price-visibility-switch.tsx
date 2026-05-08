'use client';

import { Switch } from '@/components/ui/switch';

type PriceVisibilitySwitchProps = {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
};

export function PriceVisibilitySwitch({ checked, onCheckedChange }: PriceVisibilitySwitchProps) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-3 py-2.5">
      <div>
        <p className="text-sm font-medium text-slate-800">Mostrar precio</p>
        <p className="text-xs text-slate-500">El precio se imprime en el cartel</p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  );
}
