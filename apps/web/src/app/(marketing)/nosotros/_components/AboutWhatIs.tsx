import { SiteContainer } from '@/components/layout/site-container';

export function AboutWhatIs() {
    return (
        <section className="py-20 lg:py-28">
            <SiteContainer className="mx-auto max-w-3xl text-center">
                <h2 className="font-display text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
                    ¿Qué es Mi&nbsp;Rubro?
                </h2>

                <p className="mt-5 text-base leading-relaxed text-slate-600 sm:text-lg">
                    Mi Rubro es una plataforma que reúne soluciones digitales
                    orientadas a facilitar la operación diaria de negocios
                    físicos: desde la organización interna hasta la comunicación
                    con clientes, pasando por la digitalización de menús,
                    catálogos y canales de contacto.
                </p>

                <p className="mt-4 text-base leading-relaxed text-slate-600 sm:text-lg">
                    La plataforma fue diseñada para adaptarse a distintos tipos
                    de comercios y rubros, con herramientas que pueden activarse
                    según las necesidades reales de cada negocio.
                </p>
            </SiteContainer>
        </section>
    );
}
