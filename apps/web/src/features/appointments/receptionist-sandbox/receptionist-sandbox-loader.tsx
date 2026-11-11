'use client';

import { useEffect, useRef, useState, type ComponentType, type ReactNode } from 'react';

export function ReceptionistSandboxLoader({ placeholder }: { placeholder: ReactNode }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [nearViewport, setNearViewport] = useState(false);
  const [Sandbox, setSandbox] = useState<ComponentType | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    if (typeof IntersectionObserver === 'undefined') {
      setNearViewport(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNearViewport(true);
          observer.disconnect();
        }
      },
      { rootMargin: '300px' },
    );
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!nearViewport) return;
    let cancelled = false;
    import('./receptionist-sandbox')
      .then((module) => {
        if (!cancelled) setSandbox(() => module.ReceptionistSandbox);
      })
      .catch((error: unknown) => {
        console.error('No se pudo cargar la demo del Recepcionista.', error);
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [nearViewport]);

  return (
    <div ref={containerRef} className="min-w-0">
      {Sandbox ? <Sandbox /> : placeholder}
      {loadError && (
        <p role="alert" className="mt-3 text-sm text-slate-600">
          No pudimos cargar la demo. Recargá la página para volver a intentarlo.
        </p>
      )}
    </div>
  );
}
