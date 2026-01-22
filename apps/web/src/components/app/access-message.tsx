type AccessMessageProps = {
    title: string;
    description: string;
    hint?: string;
};

export function AccessMessage({ title, description, hint }: AccessMessageProps) {
    return (
        <section className="space-y-4 rounded-3xl border border-dashed border-slate-300 bg-white p-8 text-center">
            <h2 className="text-2xl font-semibold text-slate-900">{title}</h2>
            <p className="text-sm text-slate-500">{description}</p>
            {hint ? <p className="text-xs uppercase tracking-wide text-slate-400">{hint}</p> : null}
        </section>
    );
}
