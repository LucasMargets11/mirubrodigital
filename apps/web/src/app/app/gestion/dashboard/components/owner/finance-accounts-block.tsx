"use client";

import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { ArrowRight, CreditCard, Wallet, Landmark } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { listAccounts } from '@/lib/api/treasury';
import { formatCurrency } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Account } from '@/lib/api/treasury';

type FinanceAccountsBlockProps = {
    canViewFinance: boolean;
};

export function FinanceAccountsBlock({ canViewFinance }: FinanceAccountsBlockProps) {
    const { data: accounts, isLoading } = useQuery({ 
        queryKey: ['treasury', 'accounts'], 
        queryFn: listAccounts,
        enabled: canViewFinance,
        staleTime: 60 * 1000 // 1 minute
    });

    if (!canViewFinance) return null;

    const totalBalance = accounts?.reduce((acc, account) => acc + Number(account.balance), 0) ?? 0;
    const activeAccounts = accounts?.filter(a => a.is_active) ?? [];

    const getIcon = (type: Account['type']) => {
        switch (type) {
            case 'bank': return Landmark;
            case 'cash': return Wallet;
            default: return CreditCard;
        }
    };

    if (isLoading) {
        return (
            <Card className="col-span-1 border-slate-100 animate-pulse">
                <CardHeader className="pb-2">
                    <div className="h-6 w-32 bg-slate-100 rounded" />
                </CardHeader>
                <CardContent>
                    <div className="h-10 w-24 bg-slate-100 rounded mb-4" />
                    <div className="space-y-2">
                        <div className="h-8 w-full bg-slate-50 rounded" />
                        <div className="h-8 w-full bg-slate-50 rounded" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (!accounts || accounts.length === 0) {
        return (
            <Card className="col-span-1 border-slate-100 bg-slate-50/30">
                <CardContent className="flex flex-col items-center justify-center p-6 text-center">
                    <p className="font-medium text-slate-900">Sin cuentas configuradas</p>
                    <Button variant="link" asChild className="mt-2 text-indigo-600">
                        <Link href="/app/gestion/finanzas/cuentas">Configurar cuentas</Link>
                    </Button>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="col-span-1 border-slate-200">
            <CardHeader className="flex flex-row items-center justify-between pb-2 border-b border-slate-100">
                <div className="space-y-1">
                    <CardTitle className="text-base font-semibold text-slate-900 flex items-center gap-2">
                        <Wallet className="h-5 w-5 text-slate-500" />
                        Finanzas
                    </CardTitle>
                </div>
                <Button variant="ghost" size="sm" asChild className="text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50">
                    <Link href="/app/gestion/finanzas/resumen">
                        Ver todo <ArrowRight className="ml-1 h-3 w-3" />
                    </Link>
                </Button>
            </CardHeader>
            <CardContent className="pt-6">
                <div className="mb-6">
                    <p className="text-sm font-medium text-slate-500">Saldo total consolidado</p>
                    <p className="text-3xl font-bold tracking-tight text-slate-900 mt-1">
                        {formatCurrency(totalBalance)}
                    </p>
                </div>

                <div className="space-y-3">
                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Cuentas principales</p>
                    {activeAccounts.slice(0, 3).map((account) => {
                        const Icon = getIcon(account.type);
                        return (
                            <div key={account.id} className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50 transition-colors">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-full bg-slate-100 text-slate-600">
                                        <Icon className="h-4 w-4" />
                                    </div>
                                    <div>
                                        <p className="text-sm font-medium text-slate-700">{account.name}</p>
                                        <p className="text-xs text-slate-400 capitalize">{account.type}</p>
                                    </div>
                                </div>
                                <span className={cn(
                                    "text-sm font-semibold",
                                    account.balance < 0 ? "text-red-600" : "text-slate-700"
                                )}>
                                    {formatCurrency(Number(account.balance))}
                                </span>
                            </div>
                        );
                    })}
                </div>
            </CardContent>
        </Card>
    );
}
