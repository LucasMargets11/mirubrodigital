export function toAbsoluteUrl(value?: string | null): string | undefined {
  if (!value) return undefined;

  if (value.startsWith('http://') || value.startsWith('https://')) {
    return value;
  }

  const baseUrl = process.env.NEXT_PUBLIC_SITE_URL || 'https://www.mirubro.com';

  if (value.startsWith('/')) {
    return `${baseUrl}${value}`;
  }

  return `${baseUrl}/${value}`;
}

export default toAbsoluteUrl;
