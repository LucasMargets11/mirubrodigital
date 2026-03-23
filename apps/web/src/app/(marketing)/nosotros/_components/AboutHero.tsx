import { SiteContainer } from '@/components/layout/site-container';

export function AboutHero() {
    return (
        <section className="bg-gradient-to-b from-brand-50/60 to-white py-20 lg:py-28">
            <SiteContainer className="text-center">
                <p className="text-sm font-semibold uppercase tracking-wider text-brand-600">
                    Sobre nosotros
                </p>

                <h1 className="mx-auto mt-3 max-w-3xl font-display text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
                    Sobre Mi&nbsp;Rubro
                </h1>

                <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-slate-600 sm:text-xl">
                    Somos una plataforma de herramientas digitales pensada para
                    comercios, locales gastronómicos y negocios que buscan
                    organizarse mejor, tener más presencia y conectar con sus
                    clientes de forma más simple.
                </p>
            </SiteContainer>
        </section>
    );
}
