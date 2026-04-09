# Generated migration for Deploy 3: centavos → ARS pesos help_text updates.
# help_text is metadata-only; no DB schema changes.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0011_add_qr_reviews'),
    ]

    operations = [
        migrations.AlterField(
            model_name='module',
            name='price_monthly',
            field=models.IntegerField(help_text='Price in ARS pesos (integer)'),
        ),
        migrations.AlterField(
            model_name='module',
            name='price_yearly',
            field=models.IntegerField(blank=True, help_text='Price in ARS pesos (integer)', null=True),
        ),
        migrations.AlterField(
            model_name='bundle',
            name='fixed_price_monthly',
            field=models.IntegerField(blank=True, help_text='Override price in ARS pesos (integer)', null=True),
        ),
        migrations.AlterField(
            model_name='bundle',
            name='fixed_price_yearly',
            field=models.IntegerField(blank=True, help_text='Override price in ARS pesos (integer)', null=True),
        ),
        migrations.AlterField(
            model_name='pendingsubscriptionchange',
            name='total_amount',
            field=models.IntegerField(help_text='Total amount in ARS pesos (integer)'),
        ),
    ]
