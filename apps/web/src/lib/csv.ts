type CsvSection = {
  title?: string;
  headers: string[];
  rows: Array<Array<string | number>>;
};

function escapeValue(value: string | number): string {
  const stringValue = String(value ?? '');
  if (/[",\n]/.test(stringValue)) {
    return `"${stringValue.replace(/"/g, '""')}"`;
  }
  return stringValue;
}

export function downloadCsv(filename: string, sections: CsvSection[]): void {
  const lines: string[] = [];
  sections.forEach((section, index) => {
    if (section.title) {
      lines.push(section.title);
    }
    if (section.headers.length) {
      lines.push(section.headers.map(escapeValue).join(','));
    }
    section.rows.forEach((row) => {
      lines.push(row.map(escapeValue).join(','));
    });
    if (index < sections.length - 1) {
      lines.push('');
    }
  });
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename.endsWith('.csv') ? filename : `${filename}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
