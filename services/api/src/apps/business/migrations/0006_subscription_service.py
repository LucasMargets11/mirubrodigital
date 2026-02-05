from django.db import migrations, models


def set_subscription_service(apps, schema_editor):
    Subscription = apps.get_model('business', 'Subscription')
    for subscription in Subscription.objects.select_related('business').all():
        business = getattr(subscription, 'business', None)
        default_service = getattr(business, 'default_service', 'gestion') if business else 'gestion'
        if not default_service:
            default_service = 'gestion'
        subscription.service = default_service
        subscription.save(update_fields=['service'])


def reset_subscription_service(apps, schema_editor):
    Subscription = apps.get_model('business', 'Subscription')
    Subscription.objects.update(service='gestion')


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0005_business_parent_business_status_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscription',
            name='service',
            field=models.CharField(choices=[('gestion', 'Gestion Comercial'), ('restaurante', 'Restaurantes'), ('menu_qr', 'Menú QR Online')], default='gestion', max_length=32),
        ),
        migrations.RunPython(set_subscription_service, reset_subscription_service),
    ]
