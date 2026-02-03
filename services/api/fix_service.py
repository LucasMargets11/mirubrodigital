import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from apps.accounts.models import Membership
from apps.business.models import Business, Subscription

User = get_user_model()
email = 'lapizza.owner@mirubro.local'

try:
    user = User.objects.get(email=email)
    print(f"Found user: {user.email}")
except User.DoesNotExist:
    print(f"User {email} not found")
    exit(1)

memberships = Membership.objects.filter(user=user)

for membership in memberships:
    business = membership.business
    print(f"--- Business: {business.name} (ID: {business.id}) ---")
    print(f"Current default_service: {business.default_service}")
    
    try:
        sub = business.subscription
        print(f"Subscription plan: {sub.plan}")
    except Subscription.DoesNotExist:
        print("No subscription found")
        continue

    if sub.plan == 'plus' and business.default_service != 'restaurante':
        print(f"Updating default_service to 'restaurante' for business {business.name}")
        business.default_service = 'restaurante'
        business.save()
        print("Updated.")
    elif sub.plan == 'plus':
         print(f"Service is already 'restaurante' for business {business.name}")

    # Verify context logic
    from apps.business.context import build_business_context
    context = build_business_context(business)
    print(f"Computed context service: {context.get('service')}")
    print(f"Computed context plan: {context.get('plan')}")
    print(f"Available services: {context.get('enabled_services')}")
