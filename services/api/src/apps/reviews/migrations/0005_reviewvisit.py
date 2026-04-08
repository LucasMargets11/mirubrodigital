from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0001_initial'),
        ('reviews', '0004_alter_review_status_choices'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReviewVisit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('business', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='review_visits',
                    to='business.business',
                )),
            ],
            options={
                'indexes': [
                    models.Index(fields=['business', '-created_at'], name='reviews_rev_busines_idx_visit'),
                ],
            },
        ),
    ]
