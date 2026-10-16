// Slice UI 02: selector de fecha propio (reemplaza `<input type="date">`).
// Zona del navegador "hostil" a propósito: el componente no debe depender de ella.
process.env.TZ = 'Asia/Tokyo';

import { fireEvent, render, screen, within } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Calendar, DatePicker, formatLongDate } from '../date-picker';

const TODAY = '2026-10-02';

function Harness({ initial = '', onChange = vi.fn(), ...props }: { initial?: string; onChange?: (d: string) => void; min?: string; isDateDisabled?: (d: string) => boolean }) {
    const [value, setValue] = useState(initial);
    return (
        <DatePicker
            label="Fecha"
            value={value}
            today={TODAY}
            onChange={(next) => {
                setValue(next);
                onChange(next);
            }}
            {...props}
        />
    );
}

function trigger() {
    return screen.getByRole('button', { name: /^Fecha:/ });
}

function dialog() {
    return within(screen.getByRole('dialog'));
}

function dayButton(date: string) {
    return document.querySelector(`[data-date="${date}"]`) as HTMLButtonElement;
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('formatLongDate', () => {
    it('formatea sin pasar por la zona del navegador', () => {
        expect(formatLongDate('2026-10-02')).toBe('viernes, 2 de octubre de 2026');
        expect(formatLongDate('2027-01-01')).toBe('viernes, 1 de enero de 2027');
    });
});

describe('DatePicker', () => {
    it('trigger accesible con la fecha; no usa input nativo', () => {
        render(<Harness initial="2026-10-15" />);
        expect(trigger()).toHaveAccessibleName('Fecha: jueves, 15 de octubre de 2026');
        expect(trigger()).toHaveTextContent('15 de octubre de 2026');
        expect(trigger()).toHaveAttribute('aria-expanded', 'false');
        expect(document.querySelector('input[type="date"]')).toBeNull();
    });

    it('abre el calendario en el mes del valor, con días de la semana y foco en el seleccionado', () => {
        render(<Harness initial="2026-10-15" />);
        fireEvent.click(trigger());
        expect(trigger()).toHaveAttribute('aria-expanded', 'true');
        expect(dialog().getByRole('heading', { name: 'Octubre 2026' })).toBeInTheDocument();
        expect(dialog().getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['LU', 'MA', 'MI', 'JU', 'VI', 'SA', 'DO']);
        // Grilla lunes → domingo: 28/9 abre la primera fila (días de otro mes incluidos).
        expect(dialog().getAllByRole('gridcell')[0].querySelector('button')).toHaveAttribute('data-date', '2026-09-28');
        expect(dialog().getAllByRole('gridcell')).toHaveLength(42);
        expect(dayButton('2026-10-15')).toHaveFocus();
        expect(dayButton('2026-10-15').closest('[role="gridcell"]')).toHaveAttribute('aria-selected', 'true');
        // "Hoy" marcado sin depender del color.
        expect(dayButton(TODAY)).toHaveAttribute('aria-current', 'date');
        expect(dayButton(TODAY)).toHaveAccessibleName('viernes, 2 de octubre de 2026, hoy');
    });

    it('sin valor abre en el mes de hoy', () => {
        render(<Harness />);
        expect(trigger()).toHaveTextContent('Elegí una fecha');
        fireEvent.click(trigger());
        expect(dialog().getByRole('heading', { name: 'Octubre 2026' })).toBeInTheDocument();
        expect(dayButton(TODAY)).toHaveFocus();
    });

    it('navega mes anterior / siguiente (cruza de año)', () => {
        render(<Harness initial="2026-12-10" />);
        fireEvent.click(trigger());
        fireEvent.click(dialog().getByRole('button', { name: 'Mes siguiente' }));
        expect(dialog().getByRole('heading', { name: 'Enero 2027' })).toBeInTheDocument();
        fireEvent.click(dialog().getByRole('button', { name: 'Mes anterior' }));
        fireEvent.click(dialog().getByRole('button', { name: 'Mes anterior' }));
        expect(dialog().getByRole('heading', { name: 'Noviembre 2026' })).toBeInTheDocument();
    });

    it('seleccionar un día emite YYYY-MM-DD, cierra y devuelve el foco', () => {
        const onChange = vi.fn();
        render(<Harness initial="2026-10-02" onChange={onChange} />);
        fireEvent.click(trigger());
        fireEvent.click(dayButton('2026-10-20'));
        expect(onChange).toHaveBeenCalledWith('2026-10-20');
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(trigger()).toHaveFocus();
        expect(trigger()).toHaveTextContent('20 de octubre de 2026');
    });

    it('botón Hoy elige el "hoy" recibido (no el del navegador)', () => {
        const onChange = vi.fn();
        render(<Harness initial="2027-03-05" onChange={onChange} />);
        fireEvent.click(trigger());
        fireEvent.click(dialog().getByRole('button', { name: 'Hoy' }));
        expect(onChange).toHaveBeenCalledWith(TODAY);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('teclado: flechas, PageDown, Enter y Escape', () => {
        const onChange = vi.fn();
        render(<Harness initial="2026-10-30" onChange={onChange} />);
        fireEvent.click(trigger());
        const grid = dialog().getByRole('grid');
        fireEvent.keyDown(grid, { key: 'ArrowRight' });
        expect(dayButton('2026-10-31')).toHaveFocus();
        fireEvent.keyDown(grid, { key: 'ArrowDown' });
        // Cruza al mes siguiente.
        expect(dialog().getByRole('heading', { name: 'Noviembre 2026' })).toBeInTheDocument();
        expect(dayButton('2026-11-07')).toHaveFocus();
        fireEvent.keyDown(grid, { key: 'PageDown' });
        expect(dayButton('2026-12-07')).toHaveFocus();
        fireEvent.keyDown(grid, { key: 'Escape' });
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(trigger()).toHaveFocus();
        expect(onChange).not.toHaveBeenCalled();
    });

    it('min: días pasados deshabilitados, mes anterior bloqueado y teclado no cruza el mínimo', () => {
        const onChange = vi.fn();
        render(<Harness min={TODAY} onChange={onChange} />);
        fireEvent.click(trigger());
        expect(dayButton('2026-10-01')).toBeDisabled();
        expect(dayButton('2026-10-01')).toHaveAccessibleName('jueves, 1 de octubre de 2026, no disponible');
        expect(dayButton(TODAY)).toBeEnabled();
        expect(dialog().getByRole('button', { name: 'Mes anterior' })).toBeDisabled();
        fireEvent.keyDown(dialog().getByRole('grid'), { key: 'ArrowLeft' });
        expect(dayButton(TODAY)).toHaveFocus();
        fireEvent.click(dayButton('2026-10-01'));
        expect(onChange).not.toHaveBeenCalled();
    });

    it('isDateDisabled deshabilita fechas puntuales', () => {
        render(<Harness initial={TODAY} isDateDisabled={(d) => d === '2026-10-10'} />);
        fireEvent.click(trigger());
        expect(dayButton('2026-10-10')).toBeDisabled();
        expect(dayButton('2026-10-11')).toBeEnabled();
    });

    it('click afuera cierra sin elegir', () => {
        const onChange = vi.fn();
        render(<Harness initial={TODAY} onChange={onChange} />);
        fireEvent.click(trigger());
        fireEvent.mouseDown(document.body);
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(onChange).not.toHaveBeenCalled();
    });

    it('mobile: se presenta como sheet modal con botón de cierre', () => {
        vi.stubGlobal(
            'matchMedia',
            vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
        );
        render(<Harness initial={TODAY} />);
        fireEvent.click(trigger());
        const sheet = screen.getByRole('dialog', { name: 'Elegí una fecha' });
        expect(sheet).toHaveAttribute('aria-modal', 'true');
        expect(document.body.style.overflow).toBe('hidden');
        fireEvent.click(within(sheet).getByRole('button', { name: 'Cerrar calendario' }));
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(document.body.style.overflow).toBe('');
    });
});

describe('Calendar — rango resaltado', () => {
    it('no altera la selección al resaltar la semana', () => {
        render(<Calendar value="2026-10-15" today={TODAY} onSelect={vi.fn()} highlightRange={{ from: '2026-10-12', to: '2026-10-18' }} />);
        const selected = screen.getAllByRole('gridcell').filter((c) => c.getAttribute('aria-selected') === 'true');
        expect(selected).toHaveLength(1);
        expect(selected[0].querySelector('button')).toHaveAttribute('data-date', '2026-10-15');
    });
});
