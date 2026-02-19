import { AuthForm } from '@/components/auth/auth-form';

/**
 * Login/Signup page
 * 
 * Layout structure:
 * - This page is under (auth) route group with NO footer
 * - Section takes full height of main (flex-1 from parent layout)
 * - Content is vertically centered
 * - Footer is NOT rendered (controlled by auth layout)
 */
export default function EntrarPage() {
    return (
        <section className="min-h-full flex items-center justify-center">
            <div className="w-full">
                <div className="mx-auto max-w-7xl px-6 lg:px-10">
                    <div className="grid gap-10 lg:grid-cols-2 lg:gap-16 items-center">
                        <div className="max-w-xl space-y-4">
                            <p className="text-sm font-semibold uppercase tracking-wide text-brand-500">Autenticación segura</p>
                            <h1 className="text-4xl font-display font-bold text-slate-900">Accedé a tu panel</h1>
                            <p className="text-lg text-slate-600">
                                Ingresá con tu email y contraseña para gestionar tu negocio.
                            </p>
                            <p className="text-base text-slate-500">
                                ¿No tenés cuenta? Creala en segundos y comenzá a usar todas las funcionalidades de la plataforma.
                            </p>
                        </div>
                        <div className="w-full">
                            <div className="w-full max-w-[520px] mx-auto lg:ml-auto lg:mr-0">
                                <div className="rounded-3xl border border-slate-200 bg-white/80 p-8 shadow-xl shadow-brand-500/5">
                                    <AuthForm />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
