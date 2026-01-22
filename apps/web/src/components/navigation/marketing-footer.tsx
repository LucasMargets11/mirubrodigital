export function MarketingFooter() {
    const year = new Date().getFullYear();
    return (
        <footer className="border-t border-slate-200 py-6 text-center text-sm text-slate-500">
            <p>© {year} Mirubro. Todos los derechos reservados.</p>
        </footer>
    );
}
