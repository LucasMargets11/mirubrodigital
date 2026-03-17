"use client";

import type { LucideIcon } from 'lucide-react';
import type { Route } from 'next';
import Link from 'next/link';

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
    href?: string;
    className?: string;
};

const toneStyles = {
    default: 'bg-white text-slate-900 border-slate-200',
    success: 'bg-emerald-50 text-emerald-900 border-emerald-100',
    warning: 'bg-amber-50 text-amber-900 border-amber-100',
    error: 'bg-red-50 text-red-900 border-red-100',
};

const iconToneStyles = {
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

export function KpiCard({
    title,
    value,
    subValue,
    trendLabel,
    trend = 'neutral',
    icon: Icon,
    tone = 'default',
    loading = false,
    href,
    className,
}: KpiCardProps) {
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

    const content = (
        <CardContent className="p-5 flex flex-col gap-1 h-full min-h-[120px]">
            <div className="flex items-start justify-between">
                <p className="text-sm font-medium text-slate-500 truncate pr-4">
                    {title}
                </p>
                {Icon && <Icon className={cn("h-4 w-4 shrink-0 mt-0.5", iconToneStyles[tone])} />}
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
    );

    const cardClass = cn(
        "shadow-sm overflow-hidden relative",
        toneStyles[tone],
        href && "transition-shadow hover:shadow-md focus-within:ring-2 focus-within:ring-slate-300",
        className,
    );

    if (href) {
        return (
            <Link href={href as Route} className="block rounded-xl focus:outline-none">
                <Card className={cardClass}>{content}</Card>
            </Link>
        );
    }

    return <Card className={cardClass}>{content}</Card>;
}
