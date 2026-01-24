from django.db import migrations, models
import django.db.models.deletion


def bootstrap_commercial_settings(apps, schema_editor):
    Business = apps.get_model('business', 'Business')
    CommercialSettings = apps.get_model('business', 'CommercialSettings')
    for business in Business.objects.all():
        CommercialSettings.objects.get_or_create(business=business)


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0002_business_default_service_alter_subscription_plan'),
    ]

    operations = [
        migrations.CreateModel(
            name='CommercialSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('allow_sell_without_stock', models.BooleanField(default=False)),
                ('block_sales_if_no_open_cash_session', models.BooleanField(default=True)),
                ('require_customer_for_sales', models.BooleanField(default=False)),
                ('allow_negative_price_or_discount', models.BooleanField(default=False)),
                ('warn_on_low_stock_threshold_enabled', models.BooleanField(default=True)),
                ('low_stock_threshold_default', models.PositiveIntegerField(default=5)),
                ('enable_sales_notes', models.BooleanField(default=True)),
                ('enable_receipts', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='commercial_settings', to='business.business')),
            ],
        ),
        migrations.RunPython(bootstrap_commercial_settings, migrations.RunPython.noop),
    ]
