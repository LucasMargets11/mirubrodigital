import os
import django
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model, authenticate

User = get_user_model()
email = 'lapizza.owner@mirubro.local'
password = 'mirubro123'

try:
    user = User.objects.get(email__iexact=email)
    print(f"User found: {user.username} (ID: {user.id})")
    print(f"Is active: {user.is_active}")
    print(f"Password hash: {user.password}")
    
    auth_user = authenticate(username=user.get_username(), password=password)
    if auth_user:
        print("Authentication successful!")
    else:
        print("Authentication FAILED. Password mismatch or other issue.")
        
except User.DoesNotExist:
    print(f"User with email {email} NOT FOUND.")
except Exception as e:
    print(f"Error: {e}")
