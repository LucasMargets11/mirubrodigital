"""
Blog domain models for the Mi Rubro CMS.

BlogCategory — simple categorization for posts.
BlogPost — the core editorial entity with status workflow, SEO fields,
           and structured content blocks.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class BlogCategory(models.Model):
    """Blog category for post classification."""

    slug = models.SlugField(max_length=60, unique=True)
    label = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['label']
        verbose_name_plural = 'blog categories'

    def __str__(self) -> str:
        return self.label


class BlogPost(models.Model):
    """
    Blog post with editorial workflow.

    Status transitions:
        draft → published | scheduled | archived
        scheduled → published | draft | archived
        published → draft (unpublish) | archived
        archived → draft
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Borrador'
        PUBLISHED = 'published', 'Publicado'
        SCHEDULED = 'scheduled', 'Programado'
        ARCHIVED = 'archived', 'Archivado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Core editorial fields ─────────────────────────────────────────────
    title = models.CharField(max_length=250)
    slug = models.SlugField(max_length=280, unique=True)
    excerpt = models.TextField(blank=True, default='', help_text='Short summary (1–2 sentences)')
    body_content = models.JSONField(
        default=list,
        blank=True,
        help_text='Structured content blocks (same schema as public ContentBlock[])',
    )
    cover_image_url = models.URLField(max_length=500, blank=True, default='')
    reading_time = models.CharField(max_length=20, blank=True, default='')

    # ── Categorization ────────────────────────────────────────────────────
    category = models.ForeignKey(
        BlogCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posts',
    )
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text='List of tag strings, e.g. ["inventario", "excel"]',
    )

    # ── Status / workflow ─────────────────────────────────────────────────
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    scheduled_publish_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When set with status=scheduled, Celery will publish at this time',
    )

    # ── SEO ───────────────────────────────────────────────────────────────
    meta_title = models.CharField(max_length=160, blank=True, default='')
    meta_description = models.TextField(max_length=320, blank=True, default='')
    og_title = models.CharField(max_length=160, blank=True, default='')
    og_description = models.TextField(max_length=320, blank=True, default='')
    og_image_url = models.URLField(max_length=500, blank=True, default='')
    canonical_url = models.URLField(max_length=500, blank=True, default='')

    # ── Authorship / audit ────────────────────────────────────────────────
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_posts',
    )
    last_editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_posts_edited',
    )
    source_label = models.CharField(max_length=60, default='MIRUBRO')

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['status', '-published_at']),
            models.Index(fields=['-created_at']),
        ]

    def __str__(self) -> str:
        return f'[{self.status}] {self.title}'

    # ── Slug generation ───────────────────────────────────────────────────

    def generate_unique_slug(self) -> str:
        """Generate a unique slug from the title, handling collisions."""
        base = slugify(self.title) or f'post-{str(self.id)[:8]}'
        slug = base[:270]
        counter = 1
        while BlogPost.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base[:265]}-{counter}'
            counter += 1
        return slug

    # ── SEO completeness check ────────────────────────────────────────────

    def seo_missing_fields(self) -> list[str]:
        """Return list of SEO field names that are empty."""
        missing = []
        if not self.meta_title and not self.title:
            missing.append('meta_title')
        if not self.meta_description and not self.excerpt:
            missing.append('meta_description')
        if not self.cover_image_url:
            missing.append('cover_image')
        return missing

    # ── Publication readiness ─────────────────────────────────────────────

    def validate_for_publish(self) -> list[str]:
        """Return list of validation errors that prevent publishing."""
        errors = []
        if not self.title or not self.title.strip():
            errors.append('El título es obligatorio.')
        if not self.slug or not self.slug.strip():
            errors.append('El slug es obligatorio.')
        if not self.body_content:
            errors.append('El contenido no puede estar vacío.')
        if not self.excerpt or not self.excerpt.strip():
            errors.append('El extracto es obligatorio para publicar.')
        return errors
