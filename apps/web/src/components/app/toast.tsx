import { cn } from '@/lib/utils';

export type ToastTone = 'success' | 'warning' | 'error' | 'info';

type ToastBubbleProps = {
    message: string;
    tone?: ToastTone;
    className?: string;
};

export function ToastBubble({ message, tone = 'info', className }: ToastBubbleProps) {
    const toneClasses: Record<ToastTone, string> = {
        success: 'bg-emerald-600 text-white',
        warning: 'bg-amber-500 text-slate-900',
        error: 'bg-rose-600 text-white',
        info: 'bg-slate-900 text-white',
    };

    return (
        <div
            className={cn(
                'fixed bottom-6 right-6 z-50 rounded-full px-5 py-3 text-sm font-semibold shadow-xl',
                toneClasses[tone],
                className
            )}
            role="status"
            aria-live="polite"
        >
            {message}
        </div>
    );
}
