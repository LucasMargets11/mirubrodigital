from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0008_ordersequence'),
    ]

    operations = [
        migrations.AddField(
            model_name='sale',
            name='client_order_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name='sale',
            constraint=models.UniqueConstraint(
                condition=Q(client_order_id__isnull=False),
                fields=('business', 'client_order_id'),
                name='sales_business_client_order_id_unique',
            ),
        ),
    ]