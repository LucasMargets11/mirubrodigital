import { describe, it, expect, beforeAll } from 'vitest';
import { toAbsoluteUrl } from '@/lib/url';

describe('toAbsoluteUrl', () => {
  const ORIGINAL = process.env.NEXT_PUBLIC_SITE_URL;

  beforeAll(() => {
    process.env.NEXT_PUBLIC_SITE_URL = 'https://www.mirubro.com';
  });

  it('returns undefined for empty input', () => {
    expect(toAbsoluteUrl(undefined)).toBeUndefined();
    expect(toAbsoluteUrl(null)).toBeUndefined();
  });

  it('returns same absolute url if already absolute', () => {
    const v = 'https://images.unsplash.com/photo.jpg';
    expect(toAbsoluteUrl(v)).toBe(v);
  });

  it('converts leading slash to absolute', () => {
    expect(toAbsoluteUrl('/images/foo.png')).toBe('https://www.mirubro.com/images/foo.png');
  });

  it('converts relative path without slash to absolute', () => {
    expect(toAbsoluteUrl('images/foo.png')).toBe('https://www.mirubro.com/images/foo.png');
  });

  afterAll(() => {
    process.env.NEXT_PUBLIC_SITE_URL = ORIGINAL;
  });
});
