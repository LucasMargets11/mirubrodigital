# Generated manually for menu module

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('business', '0004_alter_commercialsettings_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='MenuCategory',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('description', models.TextField(blank=True)),
                ('position', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='menu_categories', to='business.business')),
            ],
            options={
                'ordering': ['position', 'name'],
            },
        ),
        migrations.CreateModel(
            name='MenuItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('price', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('sku', models.CharField(blank=True, max_length=64)),
                ('tags', models.CharField(blank=True, max_length=255)),
                ('is_available', models.BooleanField(default=True)),
                ('is_featured', models.BooleanField(default=False)),
                ('position', models.PositiveIntegerField(default=0)),
                ('estimated_time_minutes', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='menu_items', to='business.business')),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='items', to='menu.menucategory')),
            ],
            options={
                'ordering': ['position', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='menucategory',
            constraint=models.UniqueConstraint(fields=('business', 'name'), name='menu_category_unique_name_per_business'),
        ),
        migrations.AddConstraint(
            model_name='menuitem',
            constraint=models.UniqueConstraint(condition=~models.Q(sku=''), fields=('business', 'sku'), name='menu_item_unique_sku_per_business'),
        ),
        migrations.AddIndex(
            model_name='menucategory',
            index=models.Index(fields=['business', 'position'], name='menu_cat_bus_pos_idx'),
        ),
        migrations.AddIndex(
            model_name='menucategory',
            index=models.Index(fields=['business', 'is_active'], name='menu_cat_bus_active_idx'),
        ),
        migrations.AddIndex(
            model_name='menuitem',
            index=models.Index(fields=['business', 'is_available'], name='menu_item_available_idx'),
        ),
        migrations.AddIndex(
            model_name='menuitem',
            index=models.Index(fields=['business', 'category'], name='menu_item_category_idx'),
        ),
        migrations.AddIndex(
            model_name='menuitem',
            index=models.Index(fields=['business', 'is_featured'], name='menu_item_featured_idx'),
        ),
    ]
