import { LoginForm } from '@/components/auth/login-form';

export default function LoginPage() {
    return (
        <section className="grid min-h-[calc(100vh-12rem)] gap-10 md:grid-cols-2 md:items-center">
            <div className="space-y-4">
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
            <div className="rounded-3xl border border-slate-200 bg-white/80 p-8 shadow-xl shadow-brand-500/5">
                <LoginForm />
            </div>
        </section>
    );
}
