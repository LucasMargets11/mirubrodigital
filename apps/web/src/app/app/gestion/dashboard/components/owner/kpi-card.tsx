"use client";

import { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card, CardContent } from '@/components/ui/card';

type KpiCardProps = {
    title: string;
    value: string;
    subValue?: string;
    trendLabel?: string;
    trend?: 'up' | 'down' | 'neutral';
    icon?: LucideIcon;
    tone?: 'default' | 'success' | 'warning' | 'error';
    loading?: boolean;
    className?: string;
};

export function KpiCard({
    title,
    value,
    subValue,
    trendLabel,
    trend = 'neutral',
    icon: Icon,
    tone = 'default',
    loading = false,
    className
}: KpiCardProps) {
    
    // Tone mapping
    const tones = {
        default: 'bg-white text-slate-900 border-slate-200',
        success: 'bg-emerald-50 text-emerald-900 border-emerald-100',
        warning: 'bg-amber-50 text-amber-900 border-amber-100',
        error: 'bg-red-50 text-red-900 border-red-100',
    };

    const iconTones = {
        default: 'text-slate-400',
        success: 'text-emerald-500',
        warning: 'text-amber-500',
        error: 'text-red-500',
    };

    const trendColors = {
        up: 'text-emerald-600',
        down: 'text-red-600',
        neutral: 'text-slate-500',
    };

    if (loading) {
        return (
            <Card className={cn("animate-pulse shadow-sm h-32", className)}>
                <CardContent className="h-full flex flex-col justify-between p-4">
                    <div className="h-4 w-24 rounded bg-slate-100" />
                    <div className="h-8 w-16 rounded bg-slate-100 mt-4" />
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className={cn("shadow-sm overflow-hidden relative", tones[tone], className)}>
            <CardContent className="p-5 flex flex-col gap-1 h-full min-h-[120px]">
                <div className="flex items-start justify-between">
                    <p className="text-sm font-medium text-slate-500 truncate pr-4">
                        {title}
                    </p>
                    {Icon && <Icon className={cn("h-4 w-4 shrink-0 mt-0.5", iconTones[tone])} />}
                </div>

                <div className="mt-2 flex items-baseline gap-2">
                    <span className="text-2xl font-bold tracking-tight">
                        {value}
                    </span>
                    {subValue && (
                        <span className="text-xs font-medium text-slate-400 hidden lg:inline-block">
                            {subValue}
                        </span>
                    )}
                </div>

                {trendLabel && (
                    <div className="mt-auto pt-2 flex items-center gap-1.5 text-xs font-medium">
                        <span className={cn(trendColors[trend])}>
                            {trend === 'up' && '↑'}
                            {trend === 'down' && '↓'}
                            {trend === 'neutral' && '→'}
                        </span>
                        <span className={cn(trendColors[trend])}>{trendLabel}</span>
                        <span className="text-slate-400 font-normal">vs mes ant.</span>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
