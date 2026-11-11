import type { ReactNode } from 'react';

export function SandboxLayout({
  toolbar,
  intelligence,
  conversation,
  mirubro,
}: {
  toolbar: ReactNode;
  intelligence: ReactNode;
  conversation: ReactNode;
  mirubro: ReactNode;
}) {
  return (
    <div data-testid="receptionist-sandbox" className="min-w-0 space-y-5">
      <div className="flex min-h-[124px] flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white/90 p-3 sm:min-h-16 sm:p-4">
        {toolbar}
      </div>
      <div className="grid min-w-0 grid-cols-1 items-start gap-5 md:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="order-2 min-w-0 xl:order-1">{intelligence}</div>
        <div className="order-1 h-[660px] min-w-0 md:col-span-2 md:h-[720px] xl:order-2 xl:col-span-1 xl:h-[960px]">
          {conversation}
        </div>
        <div className="order-3 min-w-0">{mirubro}</div>
      </div>
    </div>
  );
}
