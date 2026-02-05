export function Currency({ amount, currency = 'ARS' }: { amount: string | number; currency?: string }) {
    const value = typeof amount === 'string' ? parseFloat(amount) : amount;
    
    return (
        <span className="font-mono tabular-nums">
            {new Intl.NumberFormat('es-AR', {
                style: 'currency',
                currency: currency,
            }).format(value)}
        </span>
    );
}
