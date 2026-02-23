"""
Test script to debug branding logo upload
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, '/app/src')
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from src.apps.business.models import Business, BusinessBranding
from src.apps.business.serializers import BusinessBrandingSerializer
from django.test import RequestFactory

# Get first business
business = Business.objects.first()
if not business:
    print("No business found!")
    sys.exit(1)

print(f"Testing with business: {business.name}")

# Get or create branding
branding, _ = BusinessBranding.objects.get_or_create(business=business)
print(f"Branding object: {branding}")

# Create a fake image file
fake_image = SimpleUploadedFile(
    name='test.png',
    content=b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82',
    content_type='image/png'
)

# Test with FormData-like structure (single field)
print("\n=== Test 1: Single field update ===")
data = {'logo_horizontal': fake_image}
factory = RequestFactory()
request = factory.patch('/api/v1/settings/branding/')
request.user = business.members.first().user  # Assuming business has members

serializer = BusinessBrandingSerializer(
    branding,
    data=data,
    partial=True,
    context={'request': request}
)

print(f"Is valid: {serializer.is_valid()}")
if not serializer.is_valid():
    print(f"Errors: {serializer.errors}")
else:
    print("Validation passed!")
    print(f"Validated data: {serializer.validated_data}")

# Test 2: Check what data the frontend is actually sending
print("\n=== Test 2: Check empty/None values ===")
serializer2 = BusinessBrandingSerializer(
    branding,
    data={},
    partial=True,
    context={'request': request}
)
print(f"Is valid (empty data): {serializer2.is_valid()}")
if not serializer2.is_valid():
    print(f"Errors: {serializer2.errors}")
