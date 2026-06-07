/**
 * IndexedDB persistence for the offline POS sale queue (PR-OFF-04).
 *
 * Kept in a dedicated database (`mirubro-pos-offline-sales`) so it stays
 * independent from the bootstrap snapshot store and we don't have to coordinate
 * schema versions across modules. Encapsulated behind {@link OfflineSalesStorage}
 * so hooks/UI can be unit-tested against an in-memory adapter without IndexedDB.
 *
 * This layer only stores pending sales locally. It NEVER contacts the backend.
 */

import type { OfflineSaleQueueItem, OfflineSaleStatus } from './offline-sales-types';

const DB_NAME = 'mirubro-pos-offline-sales';
const DB_VERSION = 1;
const STORE_SALES = 'sales';

export interface OfflineSalesStorage {
  /** Returns all queued sales, newest first. */
  list(): Promise<OfflineSaleQueueItem[]>;
  /** Inserts a new queued sale. */
  add(item: OfflineSaleQueueItem): Promise<void>;
  /** Replaces an existing sale (matched by local_id). */
  put(item: OfflineSaleQueueItem): Promise<void>;
  /** Removes a sale by local_id. */
  remove(localId: string): Promise<void>;
  /** Counts sales, optionally filtered by status. */
  count(status?: OfflineSaleStatus): Promise<number>;
}

// ── Native IndexedDB adapter ────────────────────────────────────────────────

function isIndexedDbAvailable(): boolean {
  return typeof indexedDB !== 'undefined';
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_SALES)) {
        const store = db.createObjectStore(STORE_SALES, { keyPath: 'local_id' });
        store.createIndex('by_status', 'status', { unique: false });
        store.createIndex('by_created_at', 'created_at', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function promisifyTx(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function sortNewestFirst(items: OfflineSaleQueueItem[]): OfflineSaleQueueItem[] {
  return [...items].sort((a, b) => b.created_at.localeCompare(a.created_at));
}

class IndexedDbOfflineSalesStorage implements OfflineSalesStorage {
  async list(): Promise<OfflineSaleQueueItem[]> {
    const db = await openDb();
    try {
      const tx = db.transaction(STORE_SALES, 'readonly');
      const items = await requestToPromise<OfflineSaleQueueItem[]>(
        tx.objectStore(STORE_SALES).getAll() as IDBRequest<OfflineSaleQueueItem[]>,
      );
      return sortNewestFirst(items);
    } finally {
      db.close();
    }
  }

  async add(item: OfflineSaleQueueItem): Promise<void> {
    const db = await openDb();
    try {
      const tx = db.transaction(STORE_SALES, 'readwrite');
      tx.objectStore(STORE_SALES).add(item);
      await promisifyTx(tx);
    } finally {
      db.close();
    }
  }

  async put(item: OfflineSaleQueueItem): Promise<void> {
    const db = await openDb();
    try {
      const tx = db.transaction(STORE_SALES, 'readwrite');
      tx.objectStore(STORE_SALES).put(item);
      await promisifyTx(tx);
    } finally {
      db.close();
    }
  }

  async remove(localId: string): Promise<void> {
    const db = await openDb();
    try {
      const tx = db.transaction(STORE_SALES, 'readwrite');
      tx.objectStore(STORE_SALES).delete(localId);
      await promisifyTx(tx);
    } finally {
      db.close();
    }
  }

  async count(status?: OfflineSaleStatus): Promise<number> {
    const items = await this.list();
    return status ? items.filter((i) => i.status === status).length : items.length;
  }
}

// ── In-memory adapter (tests / SSR fallback) ────────────────────────────────

/**
 * Volatile {@link OfflineSalesStorage} for environments without IndexedDB.
 */
export class InMemoryOfflineSalesStorage implements OfflineSalesStorage {
  private items = new Map<string, OfflineSaleQueueItem>();

  async list(): Promise<OfflineSaleQueueItem[]> {
    return sortNewestFirst(
      Array.from(this.items.values()).map((i) => JSON.parse(JSON.stringify(i))),
    );
  }

  async add(item: OfflineSaleQueueItem): Promise<void> {
    if (this.items.has(item.local_id)) {
      throw new Error(`Offline sale ${item.local_id} already exists`);
    }
    this.items.set(item.local_id, JSON.parse(JSON.stringify(item)));
  }

  async put(item: OfflineSaleQueueItem): Promise<void> {
    this.items.set(item.local_id, JSON.parse(JSON.stringify(item)));
  }

  async remove(localId: string): Promise<void> {
    this.items.delete(localId);
  }

  async count(status?: OfflineSaleStatus): Promise<number> {
    const all = Array.from(this.items.values());
    return status ? all.filter((i) => i.status === status).length : all.length;
  }
}

// ── Singleton resolver ──────────────────────────────────────────────────────

let storageSingleton: OfflineSalesStorage | null = null;

/**
 * Returns the process-wide offline-sales storage adapter: IndexedDB in the
 * browser, in-memory fallback elsewhere. Lazily instantiated.
 */
export function getOfflineSalesStorage(): OfflineSalesStorage {
  if (storageSingleton) {
    return storageSingleton;
  }
  storageSingleton = isIndexedDbAvailable()
    ? new IndexedDbOfflineSalesStorage()
    : new InMemoryOfflineSalesStorage();
  return storageSingleton;
}

/** Overrides the storage adapter. Intended for tests only. */
export function __setOfflineSalesStorageForTests(
  storage: OfflineSalesStorage | null,
): void {
  storageSingleton = storage;
}

// ── High-level operations ────────────────────────────────────────────────────

/**
 * Persists a newly captured offline sale. Returns the stored item.
 * The caller is responsible for building the item (see `buildOfflineSale`).
 */
export async function enqueueOfflineSale(
  item: OfflineSaleQueueItem,
  storage: OfflineSalesStorage = getOfflineSalesStorage(),
): Promise<OfflineSaleQueueItem> {
  await storage.add(item);
  return item;
}

/** Lists queued offline sales, newest first. */
export function listOfflineSales(
  storage: OfflineSalesStorage = getOfflineSalesStorage(),
): Promise<OfflineSaleQueueItem[]> {
  return storage.list();
}

/** Counts queued offline sales, optionally by status. */
export function countOfflineSales(
  status?: OfflineSaleStatus,
  storage: OfflineSalesStorage = getOfflineSalesStorage(),
): Promise<number> {
  return storage.count(status);
}

/**
 * Removes only `synced` sales from the local queue. These already exist in the
 * backend (confirmed by the sync engine via `server_id`), so dropping them from
 * IndexedDB is safe and purely a local cleanup — no data is lost server-side.
 *
 * `pending`, `failed` and `conflict` sales are NEVER touched: they still need
 * to be synced, retried or reviewed by the operator.
 *
 * Returns the number of sales removed.
 */
export async function clearSyncedOfflineSales(
  storage: OfflineSalesStorage = getOfflineSalesStorage(),
): Promise<number> {
  const all = await storage.list();
  const synced = all.filter((s) => s.status === 'synced');
  for (const sale of synced) {
    await storage.remove(sale.local_id);
  }
  return synced.length;
}

/** Statuses removed by {@link clearResolvedAndErroredOfflineSales}. */
const CLEARABLE_HISTORY_STATUSES: ReadonlySet<OfflineSaleStatus> = new Set([
  'synced',
  'failed',
  'conflict',
]);

/**
 * "Limpiar historial" (PR-OFF-11). Clears the panel of every sale that no
 * longer needs to be sent: `synced` (already on the server), `failed` and
 * `conflict` (terminal local states the operator wants gone). These are removed
 * from IndexedDB locally.
 *
 * `pending` and `syncing` sales are NEVER removed: they still represent sales
 * that must reach the backend, so dropping them would lose money. Only states
 * in {@link CLEARABLE_HISTORY_STATUSES} are cleared.
 *
 * For this offline MVP, deleting local `failed`/`conflict` sales is an accepted
 * tradeoff: the operator explicitly asked to clear errors, and these are local
 * copies that were never accepted by the server.
 *
 * Returns the number of sales removed.
 */
export async function clearResolvedAndErroredOfflineSales(
  storage: OfflineSalesStorage = getOfflineSalesStorage(),
): Promise<number> {
  const all = await storage.list();
  const clearable = all.filter((s) => CLEARABLE_HISTORY_STATUSES.has(s.status));
  for (const sale of clearable) {
    await storage.remove(sale.local_id);
  }
  return clearable.length;
}

/**
 * Returns retryable `failed` sales back to `pending` and clears their visible
 * error (PR-OFF-09). This is the safe "Reintentar errores" / "Limpiar errores
 * reintentables" action: it NEVER deletes a sale, so no offline sale is ever
 * lost. Only transient failures (network / 5xx) are touched — those are the
 * ones the sync engine marks `retryable !== false`.
 *
 * For each reset sale we:
 * - set `status` back to `pending` (so the sync engine picks it up again),
 * - clear `last_error` (so the visual error disappears),
 * - bump `updated_at`,
 * while preserving `client_order_id`, `sale_payload`, `created_at`,
 * `sync_attempts` and every other field untouched.
 *
 * Sales in `pending`, `conflict`, `synced` and non-retryable `failed` states
 * are left exactly as they are: conflicts and hard failures must be reviewed
 * explicitly and are never silently cleared.
 *
 * Returns the number of sales reset to `pending`.
 */
export async function resetRetryableFailedOfflineSales(
  storage: OfflineSalesStorage = getOfflineSalesStorage(),
  now: string = new Date().toISOString(),
): Promise<number> {
  const all = await storage.list();
  const retryableFailed = all.filter(
    (s) => s.status === 'failed' && s.retryable !== false,
  );
  for (const sale of retryableFailed) {
    await storage.put({
      ...sale,
      status: 'pending',
      last_error: null,
      updated_at: now,
    });
  }
  return retryableFailed.length;
}
