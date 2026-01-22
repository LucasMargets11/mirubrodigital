import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';

import { TopProductsList } from './top-products-widget';

describe('TopProductsList', () => {
    it('renders empty state when there are no items', () => {
        render(<TopProductsList items={[]} metric="amount" loading={false} />);

        expect(screen.getByText(/No hay ventas en este período/i)).toBeInTheDocument();
    });
});
