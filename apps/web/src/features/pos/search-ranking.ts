/**
 * search-ranking.ts
 *
 * Pure ranking utilities for the unified POS product + category search.
 * No React dependencies — safe to unit-test in isolation.
 *
 * Ranking priority:
 *  1. Exact category match (score 1.00)
 *  2. Near-exact / fuzzy category match (score ≥ 0.70)
 *  3. Exact product match (score 1.00)
 *  4. Partial product matches (name / SKU)
 *  5. Remaining fuzzy product matches
 */

import type { PosCategory, PosProduct } from '@/types/pos-cash';

// ── Text normalisation ────────────────────────────────────────────────────────

/**
 * Lowercase, strip diacritics, collapse whitespace, trim.
 * Examples:
 *   "Coloración" → "coloracion"
 *   "  capilarr " → "capilarr"
 */
export function normalizeText(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

// ── Levenshtein distance ──────────────────────────────────────────────────────

export function levenshteinDistance(a: string, b: string): number {
  if (a === b) return 0;
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;

  const m = a.length;
  const n = b.length;

  // Use two-row rolling array for O(n) space.
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  let curr = new Array<number>(n + 1).fill(0);

  for (let i = 1; i <= m; i++) {
    curr[0] = i;
    for (let j = 1; j <= n; j++) {
      curr[j] =
        a[i - 1] === b[j - 1]
          ? prev[j - 1]
          : 1 + Math.min(prev[j], curr[j - 1], prev[j - 1]);
    }
    [prev, curr] = [curr, prev];
  }

  return prev[n];
}

// ── Similarity score ──────────────────────────────────────────────────────────

/**
 * Returns a 0–1 float indicating how well `rawQuery` matches `rawTarget`.
 *
 * Tier breakdown:
 *  1.00  exact (after normalisation)
 *  0.92  target starts with query (prefix)
 *  0.85  target contains query substring
 *  0.80  query contains target substring
 *  0.78  every query token appears in target
 *  0.70+ fuzzy on full string (edit distance ≤ 35% of max length)
 *  0.65+ fuzzy on first token of each string
 *  0.00  no match
 */
export function scoreMatch(rawQuery: string, rawTarget: string): number {
  const q = normalizeText(rawQuery);
  const t = normalizeText(rawTarget);

  if (!q || !t) return 0;
  if (q === t) return 1.0;
  if (t.startsWith(q)) return 0.92;
  if (t.includes(q)) return 0.85;
  if (q.includes(t)) return 0.80;

  // All query tokens must appear somewhere in the target text.
  const qTokens = q.split(' ').filter(Boolean);
  if (qTokens.length > 0 && qTokens.every((tok) => t.includes(tok))) return 0.78;

  // Full-string Levenshtein (only for short strings to keep cost low).
  const maxLen = Math.max(q.length, t.length);
  if (maxLen <= 20) {
    const dist = levenshteinDistance(q, t);
    const ratio = dist / maxLen;
    if (ratio <= 0.35) return Math.max(0, 0.70 - ratio * 0.5);
  }

  // First-token Levenshtein (catches typos in the first word of a multi-word name).
  const qFirst = qTokens[0] ?? '';
  const tFirst = t.split(' ')[0] ?? '';
  if (qFirst.length >= 3 && tFirst.length >= 3) {
    const tokenMax = Math.max(qFirst.length, tFirst.length);
    const dist = levenshteinDistance(qFirst, tFirst);
    const ratio = dist / tokenMax;
    if (ratio <= 0.35) return Math.max(0, 0.65 - ratio * 0.5);
  }

  return 0;
}

// ── Result types ──────────────────────────────────────────────────────────────

export interface CategorySearchResult {
  type: 'category';
  data: PosCategory;
  score: number;
}

export interface ProductSearchResult {
  type: 'product';
  data: PosProduct;
  score: number;
}

export type UnifiedSearchResult = CategorySearchResult | ProductSearchResult;

// ── Per-type matchers ─────────────────────────────────────────────────────────

export function matchCategoryResults(
  query: string,
  categories: PosCategory[],
): CategorySearchResult[] {
  if (query.length < 2) return [];

  return categories
    .map((cat): CategorySearchResult => ({
      type: 'category',
      data: cat,
      score: scoreMatch(query, cat.name),
    }))
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score);
}

export function matchProductResults(
  query: string,
  products: PosProduct[],
): ProductSearchResult[] {
  if (query.length < 2) return [];

  return products
    .map((p): ProductSearchResult => {
      const nameScore = scoreMatch(query, p.name);
      // SKU / barcode exact prefix matches get a small bump.
      const skuScore = p.sku ? scoreMatch(query, p.sku) : 0;
      const score = skuScore >= 0.92 ? Math.max(nameScore, skuScore * 0.95) : nameScore;
      return { type: 'product', data: p, score };
    })
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score);
}

// ── Unified ranking ───────────────────────────────────────────────────────────

/**
 * Threshold at which a category score qualifies to appear before any products.
 * Set conservatively so purely incidental substring matches don't hijack results.
 */
const CATEGORY_BOOST_THRESHOLD = 0.70;

/**
 * Threshold at which the category is so relevant it leads the entire result list
 * regardless of how well products match.
 */
const CATEGORY_DOMINANCE_THRESHOLD = 0.85;

/**
 * Merges and ranks category + product search results according to the priority rules.
 *
 * Rules (in order):
 *  1. If top category score ≥ DOMINANCE: show strong categories first, then products.
 *  2. If top category score ≥ BOOST and ≥ 80% of best product score: interleave by score.
 *  3. Otherwise: products first, then any qualifying categories appended at the end.
 */
export function rankSearchResults(
  query: string,
  categories: PosCategory[],
  products: PosProduct[],
  maxResults = 12,
): UnifiedSearchResult[] {
  const catResults = matchCategoryResults(query, categories);
  const prodResults = matchProductResults(query, products);

  const topCatScore = catResults[0]?.score ?? 0;
  const topProdScore = prodResults[0]?.score ?? 0;

  let merged: UnifiedSearchResult[];

  if (topCatScore >= CATEGORY_DOMINANCE_THRESHOLD) {
    // Very strong category match → lead with matching categories, then products.
    const strongCats = catResults.filter((c) => c.score >= CATEGORY_BOOST_THRESHOLD);
    merged = [...strongCats, ...prodResults.slice(0, maxResults - strongCats.length)];
  } else if (
    topCatScore >= CATEGORY_BOOST_THRESHOLD &&
    topCatScore >= topProdScore * 0.8
  ) {
    // Moderately strong category — interleave by score.
    merged = [...catResults, ...prodResults].sort((a, b) => b.score - a.score);
  } else {
    // Products dominate — append qualifying categories at the bottom.
    const qualifyingCats = catResults.filter((c) => c.score >= CATEGORY_BOOST_THRESHOLD);
    merged = [...prodResults, ...qualifyingCats];
  }

  return merged.slice(0, maxResults);
}
