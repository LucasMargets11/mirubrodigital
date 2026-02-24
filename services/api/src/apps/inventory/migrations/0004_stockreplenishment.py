import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0003_stockmovement_reason_metadata'),
        ('business', '0012_migrate_legacy_plans'),
        ('treasury', '0003_treasury_finance_full_upgrade'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='StockReplenishment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('occurred_at', models.DateTimeField()),
                ('supplier_name', models.CharField(max_length=255)),
                ('invoice_number', models.CharField(blank=True, max_length=100)),
                ('total_amount', models.DecimalField(decimal_places=4, default=0, max_digits=19)),
                ('notes', models.TextField(blank=True)),
                ('status', models.CharField(
                    choices=[('posted', 'Confirmado'), ('voided', 'Anulado')],
                    default='posted',
                    max_length=10,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stock_replenishments',
                    to='business.business',
                )),
                ('account', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='stock_replenishments',
                    to='treasury.account',
                )),
                ('transaction', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='stock_replenishment',
                    to='treasury.transaction',
                )),
                ('purchase_category', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='stock_replenishments',
                    to='treasury.transactioncategory',
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='stock_replenishments_created',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-occurred_at'],
            },
        ),
        migrations.AddIndex(
            model_name='stockreplenishment',
            index=models.Index(fields=['business', 'occurred_at'], name='inventory_r_busines_occ_idx'),
        ),
        migrations.AddIndex(
            model_name='stockreplenishment',
            index=models.Index(fields=['business', 'status'], name='inventory_r_busines_sts_idx'),
        ),
    ]
