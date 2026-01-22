"use client";

import { FormEvent, useMemo, useState } from 'react';

import { Modal } from '@/components/ui/modal';
import { ApiError } from '@/lib/api/client';

import { useCashRegisters, useOpenCashSession } from '../hooks';
import { formatCurrency } from '../utils';
import type { CashRegister } from '../types';

type OpenCashModalProps = {
    open: boolean;
    onClose: () => void;
    canManage: boolean;
};

export function OpenCashModal({ open, onClose, canManage }: OpenCashModalProps) {
    const mutation = useOpenCashSession();
    const registersQuery = useCashRegisters(open);
    const registers = registersQuery.data ?? [];

    const [selectedRegister, setSelectedRegister] = useState<string>('');
    const [openingAmount, setOpeningAmount] = useState<string>('0');
    const [error, setError] = useState<string>('');

    const activeRegisters: CashRegister[] = useMemo(() => registers.filter((register) => register.is_active), [registers]);

    const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError('');

        if (!canManage) {
            setError('Tu rol no puede abrir la caja.');
            return;
        }

        const amountValue = Number(openingAmount || 0);
        if (Number.isNaN(amountValue) || amountValue < 0) {
            setError('Ingresá un importe válido.');
            return;
        }

        try {
            await mutation.mutateAsync({
                register_id: selectedRegister || null,
                opening_cash_amount: amountValue,
            });
            setOpeningAmount('0');
            setSelectedRegister('');
            onClose();
        } catch (err) {
            const apiError = err as ApiError;
            setError(apiError.message ?? 'No pudimos abrir la caja.');
        }
    };

    return (
        <Modal open={open} title="Abrir caja" onClose={onClose}>
            <form className="space-y-4" onSubmit={handleSubmit}>
                {registersQuery.isError ? (
                    <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-700">
                        No pudimos cargar las cajas disponibles.
                    </p>
                ) : null}
                {activeRegisters.length > 1 ? (
                    <label className="block text-sm text-slate-600">
                        Seleccioná una caja
                        <select
                            className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                            value={selectedRegister}
                            onChange={(event) => setSelectedRegister(event.target.value)}
                        >
                            <option value="">Caja principal</option>
                            {activeRegisters.map((register) => (
                                <option key={register.id} value={register.id}>
                                    {register.name}
                                </option>
                            ))}
                        </select>
                    </label>
                ) : null}
                <label className="block text-sm text-slate-600">
                    Saldo inicial
                    <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={openingAmount}
                        onChange={(event) => setOpeningAmount(event.target.value)}
                        className="mt-1 w-full rounded-2xl border border-slate-200 px-4 py-2 text-base text-slate-700"
                    />
                    <span className="text-xs text-slate-400">Sugerencia: {formatCurrency(openingAmount)}</span>
                </label>
                {error ? <p className="text-sm text-rose-600">{error}</p> : null}
                <div className="flex items-center justify-end gap-2 pt-2">
                    <button
                        type="button"
                        onClick={onClose}
                        className="rounded-full border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600 hover:border-slate-900 hover:text-slate-900"
                    >
                        Cancelar
                    </button>
                    <button
                        type="submit"
                        disabled={mutation.isLoading || !canManage}
                        className="rounded-full bg-slate-900 px-5 py-2 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400"
                    >
                        {mutation.isLoading ? 'Guardando...' : 'Abrir caja'}
                    </button>
                </div>
            </form>
        </Modal>
    );
}
