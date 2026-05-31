from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0011_rename_reviews_rev_busines_updated_idx_reviews_rev_busines_17b16d_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewconfig',
            name='public_display_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Nombre público que se muestra en la landing de QR de Reseñas. '
                          'Si está vacío, se usa Business.name.',
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name='reviewconfig',
            name='public_subtitle',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Texto auxiliar debajo de la pregunta. '
                          'Si está vacío, se usa el texto por defecto.',
                max_length=180,
            ),
        ),
        migrations.AddField(
            model_name='reviewconfig',
            name='public_question',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Pregunta personalizada del componente de calificación. '
                          'Si está vacío, se genera con el nombre público.',
                max_length=180,
            ),
        ),
    ]
