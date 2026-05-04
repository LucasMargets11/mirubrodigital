from apps.billing.serializers import BundleSerializer
from apps.billing.models import Bundle

print("=== menu_qr ===")
qs = Bundle.objects.filter(vertical='menu_qr', is_active=True).order_by('sort_order', 'id')
for b in BundleSerializer(qs, many=True).data:
    print("  [{}] {:25} | {:15} | is_custom={} | price={} | badge={} | cta={}".format(
        b["sort_order"], b["code"], b["name"], b["is_custom"],
        b["fixed_price_monthly"], b["badge"], b["cta_label"]
    ))

print()
print("=== qr_reviews ===")
qs2 = Bundle.objects.filter(vertical='qr_reviews', is_active=True).order_by('sort_order', 'id')
for b in BundleSerializer(qs2, many=True).data:
    print("  [{}] {:25} | {:15} | is_custom={} | price={} | badge={} | cta={}".format(
        b["sort_order"], b["code"], b["name"], b["is_custom"],
        b["fixed_price_monthly"], b["badge"], b["cta_label"]
    ))
