"""
Add auth_provider and google_sub fields to AccountProfile.

Preparation for PR-1 (OTP) and PR-2 (Google OAuth).
Both fields are safe for existing data:
  - auth_provider defaults to 'email' (all existing users registered with email+password).
  - google_sub is nullable (no Google accounts linked yet).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0027_clear_must_change_pin'),
    ]

    operations = [
        migrations.AddField(
            model_name='accountprofile',
            name='auth_provider',
            field=models.CharField(
                choices=[('email', 'Email + Password'), ('otp', 'Email OTP'), ('google', 'Google OAuth')],
                default='email',
                help_text='Method used for initial registration. Informational — does not restrict login.',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='accountprofile',
            name='google_sub',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Google OAuth `sub` claim. Unique per Google account. NULL if never linked.',
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
    ]
