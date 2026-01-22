import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { StockAlertsPanel } from './stock-alerts-widget';

describe('StockAlertsPanel', () => {
    it('shows badge counters with provided data', () => {
        render(
            <StockAlertsPanel
                data={{
                    low_stock_threshold_default: '5.00',
                    out_of_stock_count: 2,
                    low_stock_count: 3,
                    items: [
                        { product_id: '1', name: 'Yerba 500g', stock: '0.00', threshold: '5.00', status: 'OUT' },
                    ],
                }}
                loading={false}
                cta={<span>CTA</span>}
            />,
        );

        const [outBadge] = screen.getAllByText(/Sin stock/i);
        expect(outBadge.parentElement).toHaveTextContent(/Sin stock:\s*2/);

        const [lowBadge] = screen.getAllByText(/Bajo stock/i);
        expect(lowBadge.parentElement).toHaveTextContent(/Bajo stock:\s*3/);
    });
});
