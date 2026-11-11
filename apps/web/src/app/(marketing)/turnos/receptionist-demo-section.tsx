import { SiteContainer } from '@/components/layout/site-container';
import { Badge } from '@/components/ui/badge';
import { ReceptionistSandboxLoader } from '@/features/appointments/receptionist-sandbox/receptionist-sandbox-loader';
import { SandboxPlaceholder } from '@/features/appointments/receptionist-sandbox/sandbox-placeholder';

export function ReceptionistDemoSection() {
  return (
    <section
      id="recepcionista-ia"
      aria-labelledby="recepcionista-ia-title"
      className="scroll-mt-28 bg-slate-50/60 py-16 lg:py-24"
    >
      <SiteContainer className="max-w-[1400px]">
        <div className="mx-auto mb-8 max-w-3xl text-center">
          <Badge variant="outline" className="border-brand-200 bg-white text-brand-600">
            Demo interactiva
          </Badge>
          <h2
            id="recepcionista-ia-title"
            className="mt-4 font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl"
          >
            Probá el Recepcionista IA
          </h2>
          <p className="mt-4 text-lg text-slate-600">
            Mirá cómo atiende una consulta, detecta la intención del cliente y transforma la
            conversación en información útil para tu negocio.
          </p>
          <p className="mt-3 text-sm text-slate-500">
            Esta es una simulación. No se envían mensajes ni se guardan datos.
          </p>
        </div>
        <div className="min-w-0 rounded-3xl border border-slate-200 bg-gradient-to-br from-violet-50 via-slate-100 to-emerald-50 p-2 shadow-xl shadow-slate-900/5 sm:p-5">
          <ReceptionistSandboxLoader placeholder={<SandboxPlaceholder />} />
        </div>
      </SiteContainer>
    </section>
  );
}
