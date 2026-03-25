"""Smoke test for tax_backup API endpoints."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.apps import apps
from datetime import date
import json

User = get_user_model()
Membership = apps.get_model('accounts', 'Membership')
Expense = apps.get_model('treasury', 'Expense')
FixedExpense = apps.get_model('treasury', 'FixedExpense')

results = []

def test(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, status, detail))
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))

# Setup: authenticate as gc.max (BUSINESS plan)
user_max = User.objects.get(email='gc.max@demo.local')
user_pro = User.objects.get(email='gc.pro@demo.local')

from django.conf import settings
if 'testserver' not in settings.ALLOWED_HOSTS and '*' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')

client_max = APIClient()
client_max.force_authenticate(user=user_max)
# Set business context
mem_max = Membership.objects.filter(user=user_max).first()
client_max.credentials(HTTP_X_BUSINESS_ID=str(mem_max.business_id))

client_pro = APIClient()
client_pro.force_authenticate(user=user_pro)
mem_pro = Membership.objects.filter(user=user_pro).first()
client_pro.credentials(HTTP_X_BUSINESS_ID=str(mem_pro.business_id))

BASE = '/api/v1/tax-backup'

print("\n=== SMOKE TEST: tax_backup API ===\n")

# ─── TEST 1: Entitlement Gate (gc.pro = PRO plan → should be 403) ───
print("--- Entitlement Gating ---")
r = client_pro.get(f'{BASE}/profiles/')
test("Gate: PRO plan denied (403)", r.status_code == 403, f"status={r.status_code}")

# ─── TEST 2: List profiles (gc.max = BUSINESS plan → should be 200) ───
print("\n--- Profile CRUD ---")
r = client_max.get(f'{BASE}/profiles/')
data = getattr(r, 'data', None) or json.loads(r.content) if r.content else {}
test("List profiles (200)", r.status_code == 200, f"status={r.status_code}, count={data.get('count', '?') if isinstance(data, dict) else '?'}")

# ─── TEST 3: Create expense for test, then create profile ───
# Ensure we have an expense for business 3
expense = Expense.objects.filter(business=mem_max.business).first()
if not expense:
    expense = Expense.objects.create(
        business=mem_max.business,
        name='Test - Alquiler Oficina',
        amount=50000,
        due_date=date(2026, 4, 1),
        status='pending',
    )
    print(f"  (created test expense id={expense.id})")

r = client_max.post(f'{BASE}/profiles/', {
    'expense': expense.id,
    'allocation_type': 'business',
}, format='json')
test("Create profile (201)", r.status_code == 201, f"status={r.status_code}, data={json.dumps(r.data, default=str)[:200]}")

profile_id = r.data.get('id') if r.status_code == 201 else None

# ─── TEST 4: Get profile detail ───
if profile_id:
    r = client_max.get(f'{BASE}/profiles/{profile_id}/')
    test("Get profile detail (200)", r.status_code == 200, f"status={r.status_code}, expense_name={r.data.get('expense_name','?')}")
    
    # ─── TEST 5: Upload document ───
    from django.core.files.uploadedfile import SimpleUploadedFile
    fake_pdf = SimpleUploadedFile("factura.pdf", b"%PDF-1.4 test content", content_type="application/pdf")
    r = client_max.post(f'{BASE}/profiles/{profile_id}/documents/', {
        'document_type': 'invoice',
        'period_month': 4,
        'period_year': 2026,
        'file': fake_pdf,
    }, format='multipart')
    test("Upload document (201)", r.status_code == 201, f"status={r.status_code}, data={json.dumps(r.data, default=str)[:200]}")
    
    # ─── TEST 6: Register payment ───
    r = client_max.post(f'{BASE}/profiles/{profile_id}/payments/', {
        'payment_method': 'transfer',
        'payment_date': '2026-04-01',
        'amount': '50000.00',
        'reference': 'TRF-001',
    }, format='json')
    test("Register payment (201)", r.status_code == 201, f"status={r.status_code}, data={json.dumps(r.data, default=str)[:200]}")
    
    # ─── TEST 7: Re-evaluate profile ───
    r = client_max.post(f'{BASE}/profiles/{profile_id}/re-evaluate/')
    test("Re-evaluate profile (200)", r.status_code == 200, f"status={r.status_code}, data={json.dumps(r.data, default=str)[:200]}")

else:
    test("Get profile detail", False, "skipped - no profile created")
    test("Upload document", False, "skipped - no profile created")
    test("Register payment", False, "skipped - no profile created")
    test("Re-evaluate profile", False, "skipped - no profile created")

# ─── TEST 8: Services listing ───
print("\n--- Services ---")
r = client_max.get(f'{BASE}/services/')
test("List services (200)", r.status_code == 200, f"status={r.status_code}, data={json.dumps(r.data, default=str)[:200]}")

# ─── TEST 9: Create service (linked to FixedExpense) ───
fe = FixedExpense.objects.filter(business=mem_max.business, is_active=True).first()
if fe:
    r = client_max.post(f'{BASE}/services/', {
        'fixed_expense': fe.id,
        'provider_name': 'Proveedor Test',
        'provider_tax_id': '20-12345678-9',
        'needs_monthly_invoice': True,
        'expected_document_type': 'invoice',
    }, format='json')
    test("Create service (201)", r.status_code == 201, f"status={r.status_code}, data={json.dumps(r.data, default=str)[:200]}")
    service_id = r.data.get('id') if r.status_code == 201 else None
else:
    test("Create service", False, "no FixedExpense available for business 3")
    service_id = None

# ─── TEST 10: Alerts listing ───
print("\n--- Alerts ---")
r = client_max.get(f'{BASE}/alerts/')
test("List alerts (200)", r.status_code == 200, f"status={r.status_code}, data={json.dumps(r.data, default=str)[:200]}")

# ─── TEST 11: Dashboard stats ───
print("\n--- Dashboard ---")
r = client_max.get(f'{BASE}/dashboard/')
test("Dashboard stats (200)", r.status_code == 200, f"status={r.status_code}, data={json.dumps(r.data, default=str)[:200]}")

# ─── TEST 12: Duplicates listing ───
print("\n--- Duplicates ---")
r = client_max.get(f'{BASE}/duplicates/')
test("List duplicates (200)", r.status_code == 200, f"status={r.status_code}, data={json.dumps(r.data, default=str)[:200]}")

# ─── SUMMARY ───
print("\n" + "=" * 50)
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
print(f"TOTAL: {passed} PASS / {failed} FAIL / {len(results)} tests")
if failed:
    print("\nFailed tests:")
    for name, status, detail in results:
        if status == "FAIL":
            print(f"  ✗ {name}: {detail}")
print("=" * 50)
