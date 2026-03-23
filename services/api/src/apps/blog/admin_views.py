"""
Platform admin views — Blog CMS (Phase 5).

CRUD for blog posts + categories, editorial workflow, SEO validation.
Role matrix — every endpoint requires IsAuthenticated + IsPlatformStaff + HasInternalRole:
┌─────────────────────────────────────────────────────────────────────────────┐
│ Endpoint                            │ Method │ superadmin │ content_admin  │
├─────────────────────────────────────┼────────┼────────────┼────────────────┤
│ blog/posts/                         │  GET   │     ✓      │       ✓        │
│ blog/posts/create/                  │  POST  │     ✓      │       ✓        │
│ blog/posts/kpis/                    │  GET   │     ✓      │       ✓        │
│ blog/posts/<id>/                    │  GET   │     ✓      │       ✓        │
│ blog/posts/<id>/update/             │ PATCH  │     ✓      │       ✓        │
│ blog/posts/<id>/publish/            │  POST  │     ✓      │       ✓        │
│ blog/posts/<id>/unpublish/          │  POST  │     ✓      │       ✓        │
│ blog/posts/<id>/archive/            │  POST  │     ✓      │       ✓        │
│ blog/posts/<id>/schedule/           │  POST  │     ✓      │       ✓        │
│ blog/categories/                    │GET+POST│     ✓      │       ✓        │
│ blog/categories/<id>/               │ PATCH  │     ✓      │       ✓        │
└─────────────────────────────────────┴────────┴────────────┴────────────────┘
"""
from django.db.models import Q, Count
from django.utils import timezone
from django.utils.text import slugify
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.platform_permissions import IsPlatformStaff, HasInternalRole
from apps.accounts.platform_audit import log_platform_action
from apps.blog.models import BlogPost, BlogCategory
from apps.blog import service as blog_service

PAGE_SIZE = 25


# ── Serialization helpers ─────────────────────────────────────────────────────

def _serialize_post_row(p: BlogPost) -> dict:
    return {
        'id': str(p.id),
        'title': p.title,
        'slug': p.slug,
        'status': p.status,
        'category_slug': p.category.slug if p.category else None,
        'category_label': p.category.label if p.category else None,
        'author_email': p.author.email if p.author else None,
        'author_name': p.author.get_full_name() if p.author else None,
        'excerpt': p.excerpt[:120] if p.excerpt else '',
        'cover_image_url': p.cover_image_url,
        'tags': p.tags or [],
        'seo_complete': len(p.seo_missing_fields()) == 0,
        'seo_missing': p.seo_missing_fields(),
        'created_at': p.created_at.isoformat() if p.created_at else None,
        'updated_at': p.updated_at.isoformat() if p.updated_at else None,
        'published_at': p.published_at.isoformat() if p.published_at else None,
        'scheduled_publish_at': (
            p.scheduled_publish_at.isoformat() if p.scheduled_publish_at else None
        ),
    }


def _serialize_post_detail(p: BlogPost) -> dict:
    # For published posts, link directly to the public URL.
    # For anything else, generate a secure time-limited preview token.
    if p.status == BlogPost.Status.PUBLISHED and p.slug:
        preview_url = f'/blog/{p.slug}'
    else:
        preview_url = blog_service.generate_preview_url(p)

    return {
        **_serialize_post_row(p),
        'excerpt': p.excerpt,
        'body_content': p.body_content,
        'reading_time': p.reading_time,
        'source_label': p.source_label,
        # SEO
        'meta_title': p.meta_title,
        'meta_description': p.meta_description,
        'og_title': p.og_title,
        'og_description': p.og_description,
        'og_image_url': p.og_image_url,
        'canonical_url': p.canonical_url,
        # Authorship
        'last_editor_email': p.last_editor.email if p.last_editor else None,
        'last_editor_name': p.last_editor.get_full_name() if p.last_editor else None,
        # Validation
        'publish_errors': p.validate_for_publish(),
        # Preview
        'preview_url': preview_url,
        # Public visibility flag
        'is_publicly_visible': p.status == BlogPost.Status.PUBLISHED,
    }


def _serialize_category(c: BlogCategory) -> dict:
    post_count = getattr(c, 'post_count', None)
    return {
        'id': c.id,
        'slug': c.slug,
        'label': c.label,
        'post_count': post_count if post_count is not None else 0,
        'created_at': c.created_at.isoformat() if c.created_at else None,
    }


# ── Posts: List ───────────────────────────────────────────────────────────────

class AdminBlogPostListView(APIView):
    """
    GET /api/v1/platform-admin/blog/posts/
    Query params: search, status, category, author, page, sort
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def get(self, request: Request) -> Response:
        qs = BlogPost.objects.select_related('category', 'author')

        # ── Filters ───────────────────────────────────────────────────────
        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(slug__icontains=search)
                | Q(author__email__icontains=search)
                | Q(author__first_name__icontains=search)
                | Q(author__last_name__icontains=search)
            )

        status_filter = request.query_params.get('status', '').strip()
        if status_filter:
            qs = qs.filter(status=status_filter)

        category_filter = request.query_params.get('category', '').strip()
        if category_filter:
            qs = qs.filter(category__slug=category_filter)

        author_filter = request.query_params.get('author', '').strip()
        if author_filter:
            qs = qs.filter(author__email=author_filter)

        # ── Sorting ───────────────────────────────────────────────────────
        sort = request.query_params.get('sort', '-updated_at').strip()
        allowed_sorts = {
            'updated_at', '-updated_at',
            'published_at', '-published_at',
            'created_at', '-created_at',
            'title', '-title',
        }
        if sort not in allowed_sorts:
            sort = '-updated_at'
        qs = qs.order_by(sort)

        # ── Pagination ────────────────────────────────────────────────────
        total = qs.count()
        try:
            page = max(1, int(request.query_params.get('page', '1')))
        except (ValueError, TypeError):
            page = 1
        offset = (page - 1) * PAGE_SIZE
        posts = qs[offset:offset + PAGE_SIZE]

        return Response({
            'results': [_serialize_post_row(p) for p in posts],
            'total': total,
            'page': page,
            'page_size': PAGE_SIZE,
            'total_pages': max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        })


# ── Posts: KPIs ───────────────────────────────────────────────────────────────

class AdminBlogPostKPIsView(APIView):
    """
    GET /api/v1/platform-admin/blog/posts/kpis/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def get(self, request: Request) -> Response:
        counts = {}
        for status_val, _ in BlogPost.Status.choices:
            counts[status_val] = BlogPost.objects.filter(status=status_val).count()

        return Response({
            'total': sum(counts.values()),
            'draft': counts.get('draft', 0),
            'published': counts.get('published', 0),
            'scheduled': counts.get('scheduled', 0),
            'archived': counts.get('archived', 0),
        })


# ── Posts: Create ─────────────────────────────────────────────────────────────

class AdminBlogPostCreateView(APIView):
    """
    POST /api/v1/platform-admin/blog/posts/create/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def post(self, request: Request) -> Response:
        data = request.data
        title = (data.get('title') or '').strip()
        if not title:
            return Response({'detail': 'El título es obligatorio.'}, status=400)

        post = BlogPost(
            title=title,
            excerpt=(data.get('excerpt') or '').strip(),
            body_content=data.get('body_content', []),
            cover_image_url=(data.get('cover_image_url') or '').strip(),
            reading_time=(data.get('reading_time') or '').strip(),
            tags=data.get('tags', []),
            source_label=(data.get('source_label') or 'MIRUBRO').strip(),
            # SEO
            meta_title=(data.get('meta_title') or '').strip(),
            meta_description=(data.get('meta_description') or '').strip(),
            og_title=(data.get('og_title') or '').strip(),
            og_description=(data.get('og_description') or '').strip(),
            og_image_url=(data.get('og_image_url') or '').strip(),
            canonical_url=(data.get('canonical_url') or '').strip(),
            # Author
            author=request.user,
            last_editor=request.user,
        )

        # Slug
        post.slug = blog_service.resolve_slug(post, data.get('slug'))

        # Category
        cat_slug = (data.get('category') or '').strip()
        if cat_slug:
            cat = BlogCategory.objects.filter(slug=cat_slug).first()
            if cat:
                post.category = cat

        post.save()

        log_platform_action(
            action='BLOG_POST_CREATED',
            actor=request.user,
            entity_type='blog_post',
            entity_id=str(post.id),
            details={'title': post.title, 'slug': post.slug},
        )

        return Response(_serialize_post_detail(post), status=201)


# ── Posts: Detail ─────────────────────────────────────────────────────────────

class AdminBlogPostDetailView(APIView):
    """
    GET /api/v1/platform-admin/blog/posts/<uuid:post_id>/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def get(self, request: Request, post_id: str) -> Response:
        try:
            post = BlogPost.objects.select_related('category', 'author', 'last_editor').get(pk=post_id)
        except (BlogPost.DoesNotExist, ValueError):
            return Response({'detail': 'Post no encontrado.'}, status=404)

        log_platform_action(
            action='BLOG_POST_VIEWED',
            actor=request.user,
            entity_type='blog_post',
            entity_id=str(post.id),
        )

        return Response(_serialize_post_detail(post))


# ── Posts: Update ─────────────────────────────────────────────────────────────

class AdminBlogPostUpdateView(APIView):
    """
    PATCH /api/v1/platform-admin/blog/posts/<uuid:post_id>/update/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def patch(self, request: Request, post_id: str) -> Response:
        try:
            post = BlogPost.objects.select_related('category', 'author', 'last_editor').get(pk=post_id)
        except (BlogPost.DoesNotExist, ValueError):
            return Response({'detail': 'Post no encontrado.'}, status=404)

        data = request.data
        update_fields = ['updated_at']

        # Editable fields
        field_map = {
            'title': 'title',
            'excerpt': 'excerpt',
            'body_content': 'body_content',
            'cover_image_url': 'cover_image_url',
            'reading_time': 'reading_time',
            'tags': 'tags',
            'source_label': 'source_label',
            'meta_title': 'meta_title',
            'meta_description': 'meta_description',
            'og_title': 'og_title',
            'og_description': 'og_description',
            'og_image_url': 'og_image_url',
            'canonical_url': 'canonical_url',
        }

        for key, attr in field_map.items():
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    val = val.strip()
                setattr(post, attr, val)
                update_fields.append(attr)

        # Slug update
        if 'slug' in data:
            new_slug = blog_service.resolve_slug(post, data['slug'])
            if new_slug != post.slug:
                post.slug = new_slug
                update_fields.append('slug')

        # Category
        if 'category' in data:
            cat_slug = (data['category'] or '').strip()
            if cat_slug:
                cat = BlogCategory.objects.filter(slug=cat_slug).first()
                post.category = cat
            else:
                post.category = None
            update_fields.append('category')

        post.last_editor = request.user
        update_fields.append('last_editor')
        post.save(update_fields=list(set(update_fields)))

        log_platform_action(
            action='BLOG_POST_UPDATED',
            actor=request.user,
            entity_type='blog_post',
            entity_id=str(post.id),
            details={'updated_fields': [f for f in update_fields if f != 'updated_at']},
        )

        return Response(_serialize_post_detail(post))


# ── Posts: Publish ────────────────────────────────────────────────────────────

class AdminBlogPostPublishView(APIView):
    """
    POST /api/v1/platform-admin/blog/posts/<uuid:post_id>/publish/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def post(self, request: Request, post_id: str) -> Response:
        try:
            post = BlogPost.objects.select_related('category', 'author', 'last_editor').get(pk=post_id)
        except (BlogPost.DoesNotExist, ValueError):
            return Response({'detail': 'Post no encontrado.'}, status=404)

        if not blog_service.is_valid_transition(post.status, 'published'):
            return Response(
                {'detail': f'No se puede publicar un post con estado "{post.get_status_display()}".'}, status=400
            )

        errors = blog_service.publish_post(post)
        if errors:
            return Response({'detail': 'Validación fallida.', 'errors': errors}, status=400)

        log_platform_action(
            action='BLOG_POST_PUBLISHED',
            actor=request.user,
            entity_type='blog_post',
            entity_id=str(post.id),
            details={'title': post.title, 'slug': post.slug},
        )

        return Response(_serialize_post_detail(post))


# ── Posts: Unpublish ──────────────────────────────────────────────────────────

class AdminBlogPostUnpublishView(APIView):
    """
    POST /api/v1/platform-admin/blog/posts/<uuid:post_id>/unpublish/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def post(self, request: Request, post_id: str) -> Response:
        try:
            post = BlogPost.objects.select_related('category', 'author', 'last_editor').get(pk=post_id)
        except (BlogPost.DoesNotExist, ValueError):
            return Response({'detail': 'Post no encontrado.'}, status=404)

        if not blog_service.is_valid_transition(post.status, 'draft'):
            return Response(
                {'detail': f'No se puede despublicar un post con estado "{post.get_status_display()}".'}, status=400
            )

        blog_service.unpublish_post(post)

        log_platform_action(
            action='BLOG_POST_UNPUBLISHED',
            actor=request.user,
            entity_type='blog_post',
            entity_id=str(post.id),
            details={'title': post.title},
        )

        return Response(_serialize_post_detail(post))


# ── Posts: Archive ────────────────────────────────────────────────────────────

class AdminBlogPostArchiveView(APIView):
    """
    POST /api/v1/platform-admin/blog/posts/<uuid:post_id>/archive/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def post(self, request: Request, post_id: str) -> Response:
        try:
            post = BlogPost.objects.select_related('category', 'author', 'last_editor').get(pk=post_id)
        except (BlogPost.DoesNotExist, ValueError):
            return Response({'detail': 'Post no encontrado.'}, status=404)

        if not blog_service.is_valid_transition(post.status, 'archived'):
            return Response(
                {'detail': f'No se puede archivar un post con estado "{post.get_status_display()}".'}, status=400
            )

        blog_service.archive_post(post)

        log_platform_action(
            action='BLOG_POST_ARCHIVED',
            actor=request.user,
            entity_type='blog_post',
            entity_id=str(post.id),
            details={'title': post.title},
        )

        return Response(_serialize_post_detail(post))


# ── Posts: Schedule ───────────────────────────────────────────────────────────

class AdminBlogPostScheduleView(APIView):
    """
    POST /api/v1/platform-admin/blog/posts/<uuid:post_id>/schedule/
    Body: { "publish_at": "2026-04-01T10:00:00Z" }
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def post(self, request: Request, post_id: str) -> Response:
        try:
            post = BlogPost.objects.select_related('category', 'author', 'last_editor').get(pk=post_id)
        except (BlogPost.DoesNotExist, ValueError):
            return Response({'detail': 'Post no encontrado.'}, status=404)

        if not blog_service.is_valid_transition(post.status, 'scheduled'):
            return Response(
                {'detail': f'No se puede programar un post con estado "{post.get_status_display()}".'}, status=400
            )

        publish_at_str = (request.data.get('publish_at') or '').strip()
        if not publish_at_str:
            return Response({'detail': 'Se requiere publish_at (ISO 8601).'}, status=400)

        from django.utils.dateparse import parse_datetime
        publish_at = parse_datetime(publish_at_str)
        if not publish_at:
            return Response({'detail': 'Formato de fecha inválido. Usar ISO 8601.'}, status=400)

        if timezone.is_naive(publish_at):
            publish_at = timezone.make_aware(publish_at)

        errors = blog_service.schedule_post(post, publish_at)
        if errors:
            return Response({'detail': 'Validación fallida.', 'errors': errors}, status=400)

        log_platform_action(
            action='BLOG_POST_SCHEDULED',
            actor=request.user,
            entity_type='blog_post',
            entity_id=str(post.id),
            details={'title': post.title, 'scheduled_for': publish_at.isoformat()},
        )

        return Response(_serialize_post_detail(post))


# ── Categories: List + Create ─────────────────────────────────────────────────

class AdminBlogCategoryListCreateView(APIView):
    """
    GET  /api/v1/platform-admin/blog/categories/
    POST /api/v1/platform-admin/blog/categories/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def get(self, request: Request) -> Response:
        cats = BlogCategory.objects.annotate(post_count=Count('posts')).order_by('label')
        return Response({'results': [_serialize_category(c) for c in cats]})

    def post(self, request: Request) -> Response:
        label = (request.data.get('label') or '').strip()
        if not label:
            return Response({'detail': 'Label es obligatorio.'}, status=400)

        slug = slugify(request.data.get('slug') or label)[:60]
        if BlogCategory.objects.filter(slug=slug).exists():
            return Response({'detail': f'Ya existe una categoría con slug "{slug}".'}, status=400)

        cat = BlogCategory.objects.create(slug=slug, label=label)
        return Response(_serialize_category(cat), status=201)


# ── Categories: Update ────────────────────────────────────────────────────────

class AdminBlogCategoryUpdateView(APIView):
    """
    PATCH /api/v1/platform-admin/blog/categories/<int:category_id>/
    """
    permission_classes = [IsAuthenticated, IsPlatformStaff, HasInternalRole]
    allowed_internal_roles = ['superadmin', 'content_admin']

    def patch(self, request: Request, category_id: int) -> Response:
        try:
            cat = BlogCategory.objects.get(pk=category_id)
        except BlogCategory.DoesNotExist:
            return Response({'detail': 'Categoría no encontrada.'}, status=404)

        label = (request.data.get('label') or '').strip()
        if label:
            cat.label = label

        slug_input = (request.data.get('slug') or '').strip()
        if slug_input:
            new_slug = slugify(slug_input)[:60]
            if BlogCategory.objects.filter(slug=new_slug).exclude(pk=cat.pk).exists():
                return Response({'detail': f'Ya existe una categoría con slug "{new_slug}".'}, status=400)
            cat.slug = new_slug

        cat.save()
        return Response(_serialize_category(cat))
