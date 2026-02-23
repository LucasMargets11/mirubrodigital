import { Buffer } from 'node:buffer';

import { NextResponse } from 'next/server';
import * as XLSX from 'xlsx';

// Headers completos para la importación de stock
const HEADERS = [
    'Nombre',
    'SKU',
    'Precio',
    'Costo',
    'Stock',
    'Stock mínimo',
    'Código de barras',
    'Nota',
];

// Filas de ejemplo con casos de uso comunes
const SAMPLE_ROWS = [
    // Producto completo con todos los campos
    ['Café en grano Colombia 500g', 'CF-COL-500', 3500, 1800, 25, 5, '7790000000012', 'Precio minorista sugerido'],
    // Producto con campos opcionales vacíos
    ['Filtros de papel #4 x100', 'FIL-004', 2500, 900, 40, 10, '', 'Dejar código de barras vacío si no aplica'],
    // Producto básico solo con nombre y stock
    ['Azúcar blanca 1kg', '', 1200, 600, 100, 20, '', 'SKU se genera automáticamente si está vacío'],
    // Producto para actualizar stock existente
    ['Leche descremada 1L', 'LAC-DES-1L', 850, 420, 15, 5, '7791234567890', 'Si existe, se actualizará el stock'],
];

// Instrucciones en hoja separada
const INSTRUCTIONS = [
    ['INSTRUCCIONES PARA IMPORTAR STOCK'],
    [''],
    ['1. CAMPOS OBLIGATORIOS'],
    ['   • Nombre: Nombre descriptivo del producto (obligatorio)'],
    [''],
    ['2. CAMPOS OPCIONALES'],
    ['   • SKU: Código único del producto (se genera automáticamente si está vacío)'],
    ['   • Precio: Precio de venta del producto'],
    ['   • Costo: Costo de adquisición o producción'],
    ['   • Stock: Cantidad actual en inventario (genera movimiento ADJUST si cambia)'],
    ['   • Stock mínimo: Nivel de alerta para reposición'],
    ['   • Código de barras: Código EAN, UPC o similar'],
    ['   • Nota: Observaciones o comentarios adicionales'],
    [''],
    ['3. COMPORTAMIENTO'],
    ['   • CREAR: Si el producto no existe (por nombre o SKU)'],
    ['   • ACTUALIZAR: Si encuentra coincidencia exacta por SKU o nombre'],
    ['   • AJUSTAR STOCK: Solo si el valor de Stock es diferente al actual'],
    ['   • Los movimientos de stock se crean automáticamente como tipo ADJUST'],
    [''],
    ['4. LÍMITES Y FORMATO'],
    ['   • Formato: .xlsx (Excel)'],
    ['   • Tamaño máximo: 10 MB'],
    ['   • Filas máximas: 2000'],
    ['   • Primera fila: Debe contener los encabezados'],
    ['   • Datos: Desde la fila 2 en adelante'],
    [''],
    ['5. EJEMPLOS DE NOMBRES DE COLUMNA ACEPTADOS'],
    ['   • Nombre: "Nombre", "Producto"'],
    ['   • SKU: "SKU", "Codigo", "Código"'],
    ['   • Código de barras: "Código de barras", "Codigo de barras", "Barcode"'],
    ['   • Precio: "Precio", "Precio venta"'],
    ['   • Stock mínimo: "Stock mínimo", "Stock minimo", "stock_min"'],
    ['   • Nota: "Nota", "Notas"'],
    [''],
    ['6. CONSEJOS'],
    ['   ✓ Revisá la vista previa antes de aplicar los cambios'],
    ['   ✓ Los productos duplicados se detectan automáticamente'],
    ['   ✓ Los valores numéricos no deben tener símbolos ($, %, etc.)'],
    ['   ✓ Las celdas vacías se interpretan como "sin cambios" en actualizaciones'],
    ['   ✓ Los movimientos de stock quedan registrados para auditoría'],
    [''],
    ['7. SOPORTE'],
    ['   Si tenés dudas, consultá con tu administrador o revisá la documentación.'],
];

export async function GET() {
    const workbook = XLSX.utils.book_new();
    
    // Hoja principal con datos
    const dataSheet = XLSX.utils.aoa_to_sheet([HEADERS, ...SAMPLE_ROWS]);
    
    // Configurar anchos de columna para mejor visualización
    dataSheet['!cols'] = [
        { wch: 30 },  // Nombre
        { wch: 15 },  // SKU
        { wch: 10 },  // Precio
        { wch: 10 },  // Costo
        { wch: 10 },  // Stock
        { wch: 15 },  // Stock mínimo
        { wch: 18 },  // Código de barras
        { wch: 40 },  // Nota
    ];
    
    XLSX.utils.book_append_sheet(workbook, dataSheet, 'Productos');
    
    // Hoja de instrucciones
    const instructionsSheet = XLSX.utils.aoa_to_sheet(INSTRUCTIONS);
    instructionsSheet['!cols'] = [{ wch: 80 }];
    XLSX.utils.book_append_sheet(workbook, instructionsSheet, 'Instrucciones');
    
    const arrayBuffer = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' }) as ArrayBuffer;
    const buffer = Buffer.from(arrayBuffer);

    return new NextResponse(buffer, {
        headers: {
            'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'Content-Disposition': 'attachment; filename="importar-stock-plantilla.xlsx"',
            'Cache-Control': 'public, max-age=86400',
        },
    });
}
