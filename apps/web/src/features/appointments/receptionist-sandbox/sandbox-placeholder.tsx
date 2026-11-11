import { SandboxLayout } from './sandbox-layout';

export function SandboxPlaceholder() {
  return (
    <SandboxLayout
      toolbar={
        <p className="text-sm text-slate-500">
          Reservar turno · Habilitá JavaScript para probar la demo.
        </p>
      }
      intelligence={
        <div
          aria-hidden="true"
          className="space-y-3 rounded-2xl border border-violet-200 bg-violet-50/80 p-3"
        >
          <p className="flex min-h-11 items-center px-1 text-sm font-bold text-violet-950">
            Inteligencia
          </p>
          {[108, 339, 290].map((height) => (
            <div
              key={height}
              style={{ height }}
              className="rounded-xl border border-violet-100 bg-white p-3"
            >
              <div className="h-3 w-2/3 rounded bg-slate-100" />
            </div>
          ))}
        </div>
      }
      conversation={
        <div className="flex h-full flex-col rounded-2xl border border-teal-200 bg-[#f0f7f5] p-4">
          <p className="border-b border-slate-100 pb-4 text-sm font-semibold text-slate-800">
            Conversación
          </p>
          <p className="m-auto max-w-xs text-center text-sm text-slate-500">
            Una consulta de ejemplo, desde el primer mensaje hasta la confirmación del turno.
          </p>
          <p className="text-center text-xs text-slate-400">
            Sin mensajes reales ni datos guardados
          </p>
        </div>
      }
      mirubro={
        <div
          aria-hidden="true"
          className="space-y-3 rounded-2xl border border-emerald-200 bg-emerald-50/80 p-3"
        >
          <p className="flex min-h-11 items-center px-1 text-sm font-bold text-emerald-950">
            MiRubro
          </p>
          {[
            { title: 'Contacto', height: 110 },
            { title: 'Lead', height: 116 },
            { title: 'Reserva', height: 100 },
            { title: 'Actividad de MiRubro', height: 258 },
          ].map(({ title, height }) => (
            <div
              key={title}
              style={{ minHeight: height }}
              className="rounded-xl border border-emerald-100 bg-white p-3"
            >
              <p className="text-sm font-semibold text-slate-800">{title}</p>
              <div className="mt-3 h-3 w-2/3 rounded bg-slate-100" />
            </div>
          ))}
        </div>
      }
    />
  );
}
