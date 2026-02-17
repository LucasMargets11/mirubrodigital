# Data migration: Auto-create BillingProfile and Branding for existing businesses

from django.db import migrations


def create_profiles_for_existing_businesses(apps, schema_editor):
    """
    Crear BusinessBillingProfile y BusinessBranding para todos los negocios existentes
    que no los tengan (post_save signal solo funcionará para nuevos).
    """
    Business = apps.get_model('business', 'Business')
    BusinessBillingProfile = apps.get_model('business', 'BusinessBillingProfile')
    BusinessBranding = apps.get_model('business', 'BusinessBranding')
    
    for business in Business.objects.all():
        # Crear BillingProfile si no existe
        BusinessBillingProfile.objects.get_or_create(
            business=business,
            defaults={
                'country': 'Argentina',
            }
        )
        
        # Crear Branding si no existe
        BusinessBranding.objects.get_or_create(
            business=business,
            defaults={
                'accent_color': '#000000',
            }
        )


def reverse_migration(apps, schema_editor):
    """
    Reverse: Eliminar los perfiles creados automáticamente.
    Nota: Solo elimina perfiles vacíos para evitar pérdida de datos configurados.
    """
    BusinessBillingProfile = apps.get_model('business', 'BusinessBillingProfile')
    BusinessBranding = apps.get_model('business', 'BusinessBranding')
    
    # Eliminar solo perfiles que estén completamente vacíos
    BusinessBillingProfile.objects.filter(
        legal_name='',
        tax_id='',
        legal_address='',
    ).delete()
    
    BusinessBranding.objects.filter(
        logo_horizontal='',
        logo_square='',
        accent_color='#000000',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0008_businessbillingprofile_businessbranding'),
    ]

    operations = [
        migrations.RunPython(
            create_profiles_for_existing_businesses,
            reverse_migration,
        ),
    ]
