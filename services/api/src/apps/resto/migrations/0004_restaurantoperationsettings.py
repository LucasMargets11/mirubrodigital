from django.db import migrations, models


def seed_operation_settings(apps, schema_editor):
  Business = apps.get_model('business', 'Business')
  RestaurantOperationSettings = apps.get_model('resto', 'RestaurantOperationSettings')

  existing_business_ids = set(
    RestaurantOperationSettings.objects.values_list('business_id', flat=True)
  )
  to_create = [
    RestaurantOperationSettings(business_id=business_id)
    for business_id in Business.objects.exclude(id__in=existing_business_ids).values_list('id', flat=True)
  ]
  if to_create:
    RestaurantOperationSettings.objects.bulk_create(to_create)


class Migration(migrations.Migration):

  dependencies = [
    ('business', '0024_remove_businessonboardingprogress_uq_onboarding_progress_and_more'),
    ('resto', '0003_rename_resto_table_busines_80c1f8_idx_resto_table_busines_84f759_idx'),
  ]

  operations = [
    migrations.CreateModel(
      name='RestaurantOperationSettings',
      fields=[
        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
        ('tables_enabled', models.BooleanField(default=True)),
        ('kitchen_enabled', models.BooleanField(default=True)),
        ('counter_orders_enabled', models.BooleanField(default=True)),
        ('pos_quick_sale_enabled', models.BooleanField(default=True)),
        ('allow_pickup_orders', models.BooleanField(default=True)),
        ('allow_dine_in_orders', models.BooleanField(default=True)),
        ('allow_delivery_orders', models.BooleanField(default=False)),
        ('default_pos_mode', models.CharField(choices=[('quick_sale', 'Venta rapida'), ('kitchen_order', 'Pedido a cocina')], default='quick_sale', max_length=32)),
        ('created_at', models.DateTimeField(auto_now_add=True)),
        ('updated_at', models.DateTimeField(auto_now=True)),
        ('business', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='resto_operation_settings', to='business.business')),
      ],
      options={
        'verbose_name': 'Restaurant Operation Settings',
        'verbose_name_plural': 'Restaurant Operation Settings',
      },
    ),
    migrations.RunPython(seed_operation_settings, migrations.RunPython.noop),
  ]