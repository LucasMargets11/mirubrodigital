# Stock locations PR2: cutover

PR2 changes `ProductStock` to one row per product and location. Migration
`inventory.0010_productstock_per_location` creates or reuses each business's
active primary location and assigns every unlocated balance to it, preserving
the row ID, business, product, physical quantity, and reserved quantity. An
existing assigned location is retained when it belongs to the same business.
Name collisions leave existing locations untouched and receive a suffixed
`Local principal` name. `inventory.0011_productstock_per_location` then makes
the location mandatory and replaces product's one-to-one relation with a
product/location unique constraint.

Existing APIs, workers, imports, orders, sales, reservations, and stock commands
continue to operate on the primary location. Catalog reads do not create a
location or a balance. Secondary-location management, transfers, location
selection, and location-aware movement history are not part of this release.

## Coordinated cutover

1. Stop all API instances, workers, scheduled jobs, offline-sync writers, and
   management commands that can write inventory. Drain in-flight database
   transactions before continuing.
2. Keep writers stopped while applying migrations through
   `inventory.0011_productstock_per_location`. If the backfill reports
   inconsistent business ownership, keep writers stopped and correct the
   identified rows explicitly; the migration makes no reassignment or merge.
3. Verify that every product balance has a location from the same business,
   each business has one active primary location, and the number and values of
   balance rows match the pre-migration snapshot.
4. Ensure every API instance, worker, offline-sync service, and scheduled
   command is running the PR2 code before resuming writers. Do not leave an old
   writer active: after `location` becomes non-null, an old insert that omits
   it fails at the database. This includes any old-version reader that still
   relies on `product.stock_level` or `select_related('stock_level')`: PR2
   renames that relation to `stock_levels` (a FK, no longer a `OneToOneField`),
   so an old process holding that attribute access would raise
   `AttributeError`/`RelatedObjectDoesNotExist` immediately, and an old process
   that assumes at most one `ProductStock` row per `(business, product)` (e.g.
   a `.get()` by business+product, or a report iterating without filtering by
   `location__is_primary`) would silently read a secondary-location balance or
   raise `MultipleObjectsReturned` once any future PR adds non-primary
   balances. Retire every such reader before reopening traffic, not only the
   writers.
5. Resume writers and verify primary-location stock through catalog, POS,
   sales, orders, inventory alerts, and valuation.

Each migration is atomic on PostgreSQL, but the backfill and schema changes
commit separately. Keep writers stopped across both migrations: a legacy write
between them could add an unlocated row, causing the schema migration to fail.
If the schema migration fails, the committed backfill is retained and can be
verified before retrying; do not resume old writers. Historical stock movements
remain unchanged because they did not record a location.

## Rollback boundary

Rehearsed in a disposable PostgreSQL database with two businesses, a physical
balance (quantity 13, reserved 2), a zero balance, and a business with no
balances at all:

- **Single row per product.** Migrating `0009` → `0011` and back to `0009`
  succeeds. Every row keeps its PK, business, product, quantity, and reserved
  quantity exactly. The business without any balance ends up with zero
  `ProductStock` rows both ways — the migration never creates one. `location_id`
  is **not** cleared by the rollback (migration `0010`'s reverse is a no-op by
  design); rows keep pointing at the primary location they were assigned to.
  This is harmless under the `0009` schema, where `location` is nullable, not
  a leftover bug — but it means a straight rollback does not undo the
  location assignment, only the schema and the mandatory-`location`/unique
  constraints.
- **Two locations for the same product.** Adding a second `ProductStock` row
  for the same product in a non-primary location and then rolling back to
  `0009` fails deterministically, every time, at the same point: reversing
  `inventory.0011`'s `AlterField` on `product` tries to recreate the implicit
  unique index backing the old `OneToOneField`
  (`inventory_productstock_product_id_..._uniq`) and PostgreSQL rejects it
  with `IntegrityError: could not create unique index ... Key (product_id)=(...)
  is duplicated`. Because each migration runs inside its own transaction, this
  failure rolls back cleanly: `django_migrations` still shows `0011` as the
  latest applied inventory migration, the table's constraints are untouched
  (`product_stock_product_location` still present, the old
  `product_stock_business_product` constraint still absent), and every
  `ProductStock` row keeps its original business, product, location, quantity,
  and reserved quantity. Nothing is collapsed, merged, or discarded by the
  failed attempt — it is rejected outright.

Before any product has balances in multiple locations, the schema can be
reversed if the old code is redeployed in a coordinated cutover, keeping in
mind that the rollback leaves `location_id` populated (see above) rather than
restoring a location-less state. Once multiple location rows exist for the
same product, reversing PR2 fails at the point described above rather than
merge or discard those balances. Keep PR2 running until a separately
reviewed, explicit balance consolidation has been completed; this migration
intentionally has no data-collapsing reverse operation.
