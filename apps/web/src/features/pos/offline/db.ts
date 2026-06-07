/**
 * IndexedDB persistence layer for the POS offline bootstrap snapshot
 * (PR-OFF-02B).
 *
 * Encapsulated, dependency-free wrapper over the native IndexedDB API. The
 * snapshot is split across object stores so a future PR can do fast offline
 * product lookups without re-reading the whole blob:
 *   - meta            (key 'current')  → everything except the big collections
 *   - products        (keyPath 'id')
 *   - categories      (keyPath 'id')
 *   - payment_methods (keyPath 'code')
 *
 * Persistence is exposed behind the {@link BootstrapStorage} interface so the
 * store/hooks can be unit-tested against an in-memory adapter without needing
 * IndexedDB in the test environment.
 *
 * Security: nothing sensitive is stored here — no tokens, PINs, passwords,
 * cookies, customers, sales, payments, orders, tables or kitchen state.
 */

import type {
  OfflineCategory,
  OfflinePaymentMethod,
  OfflineProduct,
  StoredPosOfflineBootstrap,
} from './types';

const DB_NAME = 'mirubro-pos-offline';
const DB_VERSION = 1;

const STORE_META = 'meta';
const STORE_PRODUCTS = 'products';
const STORE_CATEGORIES = 'categories';
const STORE_PAYMENT_METHODS = 'payment_methods';

const META_KEY = 'current';

/** Meta record = stored snapshot minus the large keyed collections. */
type MetaRecord = Omit<
  StoredPosOfflineBootstrap,
  'products' | 'categories' | 'payment_methods'
>;

export interface BootstrapStorage {
  /** Returns the full stored snapshot, or null when nothing is persisted. */
  load(): Promise<StoredPosOfflineBootstrap | null>;
  /** Atomically replaces the entire stored snapshot. */
  save(snapshot: StoredPosOfflineBootstrap): Promise<void>;
  /** Removes any stored snapshot. */
  clear(): Promise<void>;
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
      if (!db.objectStoreNames.contains(STORE_META)) {
        db.createObjectStore(STORE_META);
      }
      if (!db.objectStoreNames.contains(STORE_PRODUCTS)) {
        db.createObjectStore(STORE_PRODUCTS, { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains(STORE_CATEGORIES)) {
        db.createObjectStore(STORE_CATEGORIES, { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains(STORE_PAYMENT_METHODS)) {
        db.createObjectStore(STORE_PAYMENT_METHODS, { keyPath: 'code' });
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

function getAll<T>(store: IDBObjectStore): Promise<T[]> {
  return requestToPromise(store.getAll() as IDBRequest<T[]>);
}

class IndexedDbBootstrapStorage implements BootstrapStorage {
  async load(): Promise<StoredPosOfflineBootstrap | null> {
    const db = await openDb();
    try {
      const tx = db.transaction(
        [STORE_META, STORE_PRODUCTS, STORE_CATEGORIES, STORE_PAYMENT_METHODS],
        'readonly',
      );
      const meta = await requestToPromise<MetaRecord | undefined>(
        tx.objectStore(STORE_META).get(META_KEY) as IDBRequest<MetaRecord | undefined>,
      );
      if (!meta) {
        return null;
      }
      const products = await getAll<OfflineProduct>(tx.objectStore(STORE_PRODUCTS));
      const categories = await getAll<OfflineCategory>(tx.objectStore(STORE_CATEGORIES));
      const paymentMethods = await getAll<OfflinePaymentMethod>(
        tx.objectStore(STORE_PAYMENT_METHODS),
      );
      return {
        ...meta,
        products,
        categories,
        payment_methods: paymentMethods,
      };
    } finally {
      db.close();
    }
  }

  async save(snapshot: StoredPosOfflineBootstrap): Promise<void> {
    const db = await openDb();
    try {
      const tx = db.transaction(
        [STORE_META, STORE_PRODUCTS, STORE_CATEGORIES, STORE_PAYMENT_METHODS],
        'readwrite',
      );
      const { products, categories, payment_methods, ...meta } = snapshot;

      const metaStore = tx.objectStore(STORE_META);
      metaStore.clear();
      metaStore.put(meta, META_KEY);

      const productStore = tx.objectStore(STORE_PRODUCTS);
      productStore.clear();
      products.forEach((p) => productStore.put(p));

      const categoryStore = tx.objectStore(STORE_CATEGORIES);
      categoryStore.clear();
      categories.forEach((c) => categoryStore.put(c));

      const paymentStore = tx.objectStore(STORE_PAYMENT_METHODS);
      paymentStore.clear();
      payment_methods.forEach((m) => paymentStore.put(m));

      await promisifyTx(tx);
    } finally {
      db.close();
    }
  }

  async clear(): Promise<void> {
    const db = await openDb();
    try {
      const tx = db.transaction(
        [STORE_META, STORE_PRODUCTS, STORE_CATEGORIES, STORE_PAYMENT_METHODS],
        'readwrite',
      );
      tx.objectStore(STORE_META).clear();
      tx.objectStore(STORE_PRODUCTS).clear();
      tx.objectStore(STORE_CATEGORIES).clear();
      tx.objectStore(STORE_PAYMENT_METHODS).clear();
      await promisifyTx(tx);
    } finally {
      db.close();
    }
  }
}

// ── In-memory adapter (tests / SSR fallback) ────────────────────────────────

/**
 * Volatile {@link BootstrapStorage} used in environments without IndexedDB
 * (server-side, unit tests). Holds a single snapshot in memory.
 */
export class InMemoryBootstrapStorage implements BootstrapStorage {
  private snapshot: StoredPosOfflineBootstrap | null = null;

  async load(): Promise<StoredPosOfflineBootstrap | null> {
    return this.snapshot;
  }

  async save(snapshot: StoredPosOfflineBootstrap): Promise<void> {
    // Deep clone to mimic structured-clone persistence semantics.
    this.snapshot = JSON.parse(JSON.stringify(snapshot));
  }

  async clear(): Promise<void> {
    this.snapshot = null;
  }
}

// ── Singleton resolver ──────────────────────────────────────────────────────

let storageSingleton: BootstrapStorage | null = null;

/**
 * Returns the process-wide storage adapter: IndexedDB in the browser, an
 * in-memory fallback elsewhere. Lazily instantiated.
 */
export function getBootstrapStorage(): BootstrapStorage {
  if (storageSingleton) {
    return storageSingleton;
  }
  storageSingleton = isIndexedDbAvailable()
    ? new IndexedDbBootstrapStorage()
    : new InMemoryBootstrapStorage();
  return storageSingleton;
}

/**
 * Overrides the storage adapter. Intended for tests only.
 */
export function __setBootstrapStorageForTests(storage: BootstrapStorage | null): void {
  storageSingleton = storage;
}
