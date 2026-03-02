# Generated manually 2026-02-28

import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0001_initial'),
        ('menu', '0007_rename_menu_tiptra_busines_idx_menu_tiptra_busines_dc0b84_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='MenuLayoutBlock',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=120)),
                ('position', models.PositiveIntegerField(default=0)),
                ('layout', models.CharField(
                    choices=[('stack', 'Lista (stack)'), ('grid', 'Cuadrícula (grid)')],
                    default='stack',
                    max_length=16,
                )),
                ('columns_desktop', models.PositiveSmallIntegerField(default=3)),
                ('columns_tablet', models.PositiveSmallIntegerField(default=2)),
                ('columns_mobile', models.PositiveSmallIntegerField(default=1)),
                ('badge_text', models.CharField(blank=True, max_length=80)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('business', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='menu_layout_blocks',
                    to='business.business',
                )),
            ],
            options={
                'ordering': ['position', 'title'],
            },
        ),
        migrations.AddIndex(
            model_name='menulayoutblock',
            index=models.Index(fields=['business', 'position'], name='menu_layout_business_position_idx'),
        ),
        migrations.CreateModel(
            name='MenuLayoutBlockCategory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('position', models.PositiveIntegerField(default=0)),
                ('block', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='block_categories',
                    to='menu.menulayoutblock',
                )),
                ('category', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='block_memberships',
                    to='menu.menucategory',
                )),
            ],
            options={
                'ordering': ['position', 'category__name'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='menulayoutblockcategory',
            unique_together={('block', 'category')},
        ),
        migrations.AddField(
            model_name='menulayoutblock',
            name='categories',
            field=models.ManyToManyField(
                blank=True,
                related_name='layout_blocks',
                through='menu.MenuLayoutBlockCategory',
                to='menu.menucategory',
            ),
        ),
    ]
