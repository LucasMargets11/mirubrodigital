"""
Phase 5 — Blog CMS models + audit actions.

Creates:
  - blog_blogcategory: simple categorization for posts
  - blog_blogpost: full editorial entity with status workflow, SEO, content blocks

Also adds 7 new audit actions to AccessAuditLog:
  BLOG_POST_CREATED, BLOG_POST_UPDATED, BLOG_POST_PUBLISHED,
  BLOG_POST_UNPUBLISHED, BLOG_POST_ARCHIVED, BLOG_POST_SCHEDULED, BLOG_POST_VIEWED
"""
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='BlogCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(max_length=60, unique=True)),
                ('label', models.CharField(max_length=120)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'blog categories',
                'ordering': ['label'],
            },
        ),
        migrations.CreateModel(
            name='BlogPost',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=250)),
                ('slug', models.SlugField(max_length=280, unique=True)),
                ('excerpt', models.TextField(blank=True, default='', help_text='Short summary (1–2 sentences)')),
                ('body_content', models.JSONField(blank=True, default=list, help_text='Structured content blocks (same schema as public ContentBlock[])')),
                ('cover_image_url', models.URLField(blank=True, default='', max_length=500)),
                ('reading_time', models.CharField(blank=True, default='', max_length=20)),
                ('tags', models.JSONField(blank=True, default=list, help_text='List of tag strings, e.g. ["inventario", "excel"]')),
                ('status', models.CharField(choices=[('draft', 'Borrador'), ('published', 'Publicado'), ('scheduled', 'Programado'), ('archived', 'Archivado')], db_index=True, default='draft', max_length=16)),
                ('published_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('scheduled_publish_at', models.DateTimeField(blank=True, help_text='When set with status=scheduled, Celery will publish at this time', null=True)),
                ('meta_title', models.CharField(blank=True, default='', max_length=160)),
                ('meta_description', models.TextField(blank=True, default='', max_length=320)),
                ('og_title', models.CharField(blank=True, default='', max_length=160)),
                ('og_description', models.TextField(blank=True, default='', max_length=320)),
                ('og_image_url', models.URLField(blank=True, default='', max_length=500)),
                ('canonical_url', models.URLField(blank=True, default='', max_length=500)),
                ('source_label', models.CharField(default='MIRUBRO', max_length=60)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='blog_posts', to=settings.AUTH_USER_MODEL)),
                ('last_editor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='blog_posts_edited', to=settings.AUTH_USER_MODEL)),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='posts', to='blog.blogcategory')),
            ],
            options={
                'ordering': ['-updated_at'],
            },
        ),
        migrations.AddIndex(
            model_name='blogpost',
            index=models.Index(fields=['status', '-published_at'], name='blog_blogpo_status_idx'),
        ),
        migrations.AddIndex(
            model_name='blogpost',
            index=models.Index(fields=['-created_at'], name='blog_blogpo_created_idx'),
        ),
    ]
