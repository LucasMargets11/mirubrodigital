'use client';

import { type SeatInfo, getEffectiveLimit } from '@/types/owner-access';

interface SeatInfoBarProps {
    seatInfo: SeatInfo;
}

export function SeatInfoBar({ seatInfo }: SeatInfoBarProps) {
    const { current, access_granted } = seatInfo;
    const effectiveLimit = getEffectiveLimit(seatInfo);

    // State 3: subscription inactive
    if (!access_granted) {
        return (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
                <div className="flex items-center gap-2">
                    <svg className="h-5 w-5 flex-shrink-0 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                    </svg>
                    <p className="text-sm font-medium text-red-800">
                        Suscripción inactiva. No podés agregar usuarios.
                    </p>
                </div>
            </div>
        );
    }

    // State 4: data error — effectiveLimit=0 but access_granted=true
    if (effectiveLimit === 0) {
        return (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <div className="flex items-center gap-2">
                    <svg className="h-5 w-5 flex-shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <p className="text-sm font-medium text-amber-800">
                        No pudimos determinar el límite. Contactá soporte.
                    </p>
                </div>
            </div>
        );
    }

    const isAtLimit = current >= effectiveLimit;
    const percentage = Math.min(Math.round((current / effectiveLimit) * 100), 100);

    // State 2: at or over limit
    if (isAtLimit) {
        return (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <svg className="h-5 w-5 flex-shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                        <p className="text-sm font-medium text-amber-800">
                            Has alcanzado el límite de usuarios secundarios
                        </p>
                    </div>
                    <span className="text-sm font-semibold text-amber-700">
                        {current}/{effectiveLimit}
                    </span>
                </div>
                <div className="mt-2 h-1.5 w-full rounded-full bg-amber-200">
                    <div className="h-1.5 rounded-full bg-amber-500" style={{ width: '100%' }} />
                </div>
            </div>
        );
    }

    // State 1: normal — under the limit
    return (
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="flex items-center justify-between">
                <p className="text-sm text-slate-700">
                    <span className="font-medium">{current}</span>/{effectiveLimit} usuarios secundarios
                </p>
                <span className="text-xs text-slate-500">
                    {effectiveLimit - current} disponible{effectiveLimit - current !== 1 ? 's' : ''}
                </span>
            </div>
            <div className="mt-2 h-1.5 w-full rounded-full bg-slate-200">
                <div
                    className="h-1.5 rounded-full bg-blue-500 transition-all"
                    style={{ width: `${percentage}%` }}
                />
            </div>
        </div>
    );
}
