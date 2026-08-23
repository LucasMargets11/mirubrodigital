/**
 * PR-B — QrReviewsPlanBuilder pricing + plan_code regression tests.
 *
 * Validates:
 *   - Base muestra $15.000 y Pro muestra $20.000 (solo mensual).
 *   - onSubscribe envía los plan_code canónicos qr_reviews_base / qr_reviews_pro
 *     (NO los códigos legacy reviews_base / reviews_pro).
 *   - Las cards conservan el split de features de PR-A.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

import { QrReviewsPlanBuilder } from '../QrReviewsPlanBuilder';

describe('QrReviewsPlanBuilder — PR-B pricing', () => {
    it('shows $15.000 for Base and $20.000 for Pro in monthly mode', () => {
        render(<QrReviewsPlanBuilder billingPeriod="monthly" onSubscribe={() => {}} />);

        expect(screen.getAllByText(/Reseñas Base/i).length).toBeGreaterThan(0);
        expect(screen.getAllByText(/Reseñas Pro/i).length).toBeGreaterThan(0);

        expect(screen.getByText(/15\.000/)).toBeInTheDocument();
        expect(screen.getByText(/20\.000/)).toBeInTheDocument();

        expect(screen.queryByText(/25\.000/)).not.toBeInTheDocument();
        expect(screen.queryByText(/28\.000/)).not.toBeInTheDocument();
        expect(screen.queryByText(/40\.000/)).not.toBeInTheDocument();
    });

    it('does not show yearly pricing or annual discount for QR de Reseñas', () => {
        render(<QrReviewsPlanBuilder billingPeriod="monthly" onSubscribe={() => {}} />);

        expect(screen.queryByText(/144\.000/)).not.toBeInTheDocument();
        expect(screen.queryByText(/192\.000/)).not.toBeInTheDocument();
        expect(screen.queryByText(/año/)).not.toBeInTheDocument();
        expect(screen.queryByText(/anual/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/Ahorrás 20%/)).not.toBeInTheDocument();
    });

    it('Base CTA invokes onSubscribe with canonical plan_code "qr_reviews_base"', () => {
        const onSubscribe = vi.fn();
        render(<QrReviewsPlanBuilder billingPeriod="monthly" onSubscribe={onSubscribe} />);

        const baseCta = screen.getByRole('button', { name: /Activar Reseñas Base/i });
        fireEvent.click(baseCta);

        expect(onSubscribe).toHaveBeenCalledTimes(1);
        expect(onSubscribe).toHaveBeenCalledWith({ planCode: 'qr_reviews_base' });
    });

    it('Pro CTA invokes onSubscribe with canonical plan_code "qr_reviews_pro"', () => {
        const onSubscribe = vi.fn();
        render(<QrReviewsPlanBuilder billingPeriod="monthly" onSubscribe={onSubscribe} />);

        const proCta = screen.getByRole('button', { name: /Activar Reseñas Pro/i });
        fireEvent.click(proCta);

        expect(onSubscribe).toHaveBeenCalledTimes(1);
        expect(onSubscribe).toHaveBeenCalledWith({ planCode: 'qr_reviews_pro' });
    });

    it('does NOT emit the legacy short codes reviews_base / reviews_pro', () => {
        const onSubscribe = vi.fn();
        render(<QrReviewsPlanBuilder billingPeriod="monthly" onSubscribe={onSubscribe} />);

        fireEvent.click(screen.getByRole('button', { name: /Activar Reseñas Base/i }));
        fireEvent.click(screen.getByRole('button', { name: /Activar Reseñas Pro/i }));

        const codes = onSubscribe.mock.calls.map((c) => (c[0] as { planCode: string }).planCode);
        expect(codes).not.toContain('reviews_base');
        expect(codes).not.toContain('reviews_pro');
        expect(codes).toEqual(['qr_reviews_base', 'qr_reviews_pro']);
    });

    it('keeps PR-A feature split (Base = filtro/feedback, Pro = carteles/analytics/estados)', () => {
        const { container } = render(
            <QrReviewsPlanBuilder billingPeriod="monthly" onSubscribe={() => {}} />,
        );

        // Find both card roots by their CTA buttons' enclosing container
        const baseCard = screen
            .getByRole('button', { name: /Activar Reseñas Base/i })
            .closest('div.h-full');
        const proCard = screen
            .getByRole('button', { name: /Activar Reseñas Pro/i })
            .closest('div.h-full');

        expect(baseCard).toBeTruthy();
        expect(proCard).toBeTruthy();

        const baseText = (baseCard as HTMLElement).textContent ?? '';
        const proText = (proCard as HTMLElement).textContent ?? '';

        // Base: filtro inteligente + feedback privado, sin carteles/analytics/estados
        expect(baseText).toMatch(/Filtro inteligente/i);
        expect(baseText).toMatch(/Feedback privado/i);
        expect(baseText).not.toMatch(/Carteles profesionales/i);
        expect(baseText).not.toMatch(/Analytics avanzadas/i);
        expect(baseText).not.toMatch(/Estados de gestión/i);

        // Pro: carteles, analytics, estados, métricas
        expect(proText).toMatch(/Carteles profesionales/i);
        expect(proText).toMatch(/Analytics avanzadas/i);
        expect(proText).toMatch(/Estados de gestión/i);
        expect(proText).toMatch(/Métricas de conversión/i);

        // Eliminar warning de variable container/within no usadas
        expect(container).toBeTruthy();
        void within;
    });
});
