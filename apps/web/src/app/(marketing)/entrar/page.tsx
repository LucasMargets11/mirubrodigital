import { LoginForm } from '@/components/auth/login-form';

export default function LoginPage() {
    return (
        <section className="flex-1 min-h-[calc(100dvh-4rem)] flex items-start md:items-center py-10 md:py-0">
            <div className="w-full">
                <div className="mx-auto max-w-7xl px-6 lg:px-10">
                    <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
                        <div className="max-w-xl space-y-4">
                            <p className="text-sm font-semibold uppercase tracking-wide text-brand-500">Autenticación segura</p>
                            <h1 className="text-4xl font-display font-bold text-slate-900">Entrar a tu panel multi-tenant</h1>
                            <p className="text-slate-600">
                                Usa tus credenciales de Mirubro o crea un usuario con
                                <code className="mx-1 rounded bg-slate-100 px-2 py-1 text-xs font-mono text-slate-700">
                                    python manage.py createsuperuser
                                </code>
                                para comenzar a probar la experiencia protegida por JWT.
                            </p>
                        </div>
                        <div className="justify-self-end w-full">
                            <div className="w-full max-w-[520px]">
                                <div className="rounded-3xl border border-slate-200 bg-white/80 p-8 shadow-xl shadow-brand-500/5">
                                    <LoginForm />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    );
}
