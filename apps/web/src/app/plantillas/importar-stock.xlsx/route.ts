import { Buffer } from 'node:buffer';

import { NextResponse } from 'next/server';
import * as XLSX from 'xlsx';

const HEADERS = ['Nombre', 'SKU', 'Precio', 'Costo', 'Stock', 'Stock mínimo', 'Código de barras', 'Nota'];
const SAMPLE_ROWS = [
    ['Café en grano', 'CF-001', 3500, 1800, 25, 5, '7790000000012', 'Precio minorista sugerido'],
    ['Filtros #4', 'FIL-004', 2500, 900, 40, 10, '', 'Opcional'],
];

export async function GET() {
    const workbook = XLSX.utils.book_new();
    const sheet = XLSX.utils.aoa_to_sheet([HEADERS, ...SAMPLE_ROWS]);
    XLSX.utils.book_append_sheet(workbook, sheet, 'Importar stock');
    const arrayBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' }) as ArrayBuffer;
    const buffer = Buffer.from(arrayBuffer);

    return new NextResponse(buffer, {
        headers: {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': 'attachment; filename="importar-stock.xlsx"',
            'Cache-Control': 'public, max-age=86400',
        },
    });
}
