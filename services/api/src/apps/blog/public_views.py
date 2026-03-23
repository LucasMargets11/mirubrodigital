"""
Public read-only views for the blog.

These endpoints serve published content to the storefront/web and require
NO authentication.  Drafts, scheduled-future, and archived posts are
never returned — except through the secure preview endpoint, which
validates a time-limited HMAC token.

Permissions: AllowAny (public internet).
"""
from __future__ import annotations

import hashlib
import hmac
import time

from django.conf import settings
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.blog.models import BlogPost, BlogCategory
from apps.accounts.platform_audit import log_platform_action

# ── Constants ─────────────────────────────────────────────────────────────────

PUBLIC_PAGE_SIZE = 12
PREVIEW_TOKEN_MAX_AGE = 3600  # 1 hour


# ── Helpers ───────────────────────────────────────────────────────────────────

def _public_post_summary(p: BlogPost) -> dict:
    """Lightweight representation for list views / cards."""
    return {
        'slug': p.slug,
        'title': p.title,
        'excerpt': p.excerpt,
        'cover_image_url': p.cover_image_url,
        'reading_time': p.reading_time,
        'date': p.published_at.isoformat() if p.published_at else p.created_at.isoformat(),
        'source_label': p.source_label,
        'category_slug': p.category.slug if p.category else None,
        'category_label': p.category.label if p.category else None,
        'author_name': p.author.get_full_name() if p.author else None,
        # SEO (needed by the home section)
        'meta_title': p.meta_title or p.title,
        'meta_description': p.meta_description or p.excerpt,
    }


def _public_post_detail(p: BlogPost) -> dict:
    """Full representation for the detail page."""
    return {
        **_public_post_summary(p),
        'body_content': p.body_content,
        'tags': p.tags or [],
        # SEO
        'og_title': p.og_title or p.meta_title or p.title,
        'og_description': p.og_description or p.meta_description or p.excerpt,
        'og_image_url': p.og_image_url or p.cover_image_url,
        'canonical_url': p.canonical_url or '',
    }


def _published_queryset():
    """Return only publicly-visible posts: published status."""
    return (
        BlogPost.objects
        .filter(status=BlogPost.Status.PUBLISHED)
        .select_related('category', 'author')
        .order_by('-published_at')
    )


def _generate_preview_token(post_id: str, ts: int) -> str:
    """HMAC-SHA256 token for time-limited post preview."""
    secret = getattr(settings, 'SECRET_KEY', '')
    message = f'blog-preview:{post_id}:{ts}'
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def _verify_preview_token(post_id: str, token: str, ts_str: str) -> bool:
    """Verify an HMAC preview token is valid and not expired."""
    try:
        ts = int(ts_str)
    except (ValueError, TypeError):
        return False
    if time.time() - ts > PREVIEW_TOKEN_MAX_AGE:
        return False
    expected = _generate_preview_token(post_id, ts)
    return hmac.compare_digest(expected, token)


# ── Public list ───────────────────────────────────────────────────────────────

class PublicBlogPostListView(APIView):
    """
    GET /api/v1/blog/posts/
    Query params: page, category
    Returns only *published* posts ordered by published_at desc.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request: Request) -> Response:
        qs = _published_queryset()

        # Optional category filter
        category = request.query_params.get('category', '').strip()
        if category:
            qs = qs.filter(category__slug=category)

        total = qs.count()
        try:
            page = max(1, int(request.query_params.get('page', '1')))
        except (ValueError, TypeError):
            page = 1
        offset = (page - 1) * PUBLIC_PAGE_SIZE
        posts = qs[offset:offset + PUBLIC_PAGE_SIZE]

        return Response({
            'results': [_public_post_summary(p) for p in posts],
            'total': total,
            'page': page,
            'page_size': PUBLIC_PAGE_SIZE,
            'total_pages': max(1, (total + PUBLIC_PAGE_SIZE - 1) // PUBLIC_PAGE_SIZE),
        })


# ── Public detail ─────────────────────────────────────────────────────────────

class PublicBlogPostDetailView(APIView):
    """
    GET /api/v1/blog/posts/<slug>/
    Returns a single published post.  404 for draft/scheduled/archived.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request: Request, slug: str) -> Response:
        try:
            post = (
                BlogPost.objects
                .select_related('category', 'author')
                .get(slug=slug, status=BlogPost.Status.PUBLISHED)
            )
        except BlogPost.DoesNotExist:
            return Response({'detail': 'Post no encontrado.'}, status=404)

        return Response(_public_post_detail(post))


# ── Public categories ─────────────────────────────────────────────────────────

class PublicBlogCategoryListView(APIView):
    """
    GET /api/v1/blog/categories/
    Returns categories that have at least one published post.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request: Request) -> Response:
        cats = (
            BlogCategory.objects
            .filter(posts__status=BlogPost.Status.PUBLISHED)
            .distinct()
            .order_by('label')
        )
        return Response({
            'results': [
                {'slug': c.slug, 'label': c.label}
                for c in cats
            ]
        })


# ── Preview (token-protected) ────────────────────────────────────────────────

class PublicBlogPostPreviewView(APIView):
    """
    GET /api/v1/blog/preview/<post_id>/?token=...&ts=...
    Time-limited HMAC-protected preview of any post (including drafts).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request: Request, post_id: str) -> Response:
        token = request.query_params.get('token', '')
        ts = request.query_params.get('ts', '')

        if not _verify_preview_token(post_id, token, ts):
            return Response({'detail': 'Token de preview inválido o expirado.'}, status=403)

        try:
            post = (
                BlogPost.objects
                .select_related('category', 'author')
                .get(pk=post_id)
            )
        except (BlogPost.DoesNotExist, ValueError):
            return Response({'detail': 'Post no encontrado.'}, status=404)

        data = _public_post_detail(post)
        data['is_preview'] = True
        data['status'] = post.status

        log_platform_action(
            action='BLOG_POST_PREVIEWED',
            actor=None,
            entity_type='blog_post',
            entity_id=str(post.id),
            details={'status': post.status, 'slug': post.slug},
        )

        return Response(data)


# ── Sitemap feed ──────────────────────────────────────────────────────────────

class PublicBlogSitemapView(APIView):
    """
    GET /api/v1/blog/sitemap/
    Returns slug + published_at for all published posts (for sitemap generation).
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request: Request) -> Response:
        posts = (
            BlogPost.objects
            .filter(status=BlogPost.Status.PUBLISHED)
            .values_list('slug', 'published_at')
            .order_by('-published_at')
        )
        return Response({
            'posts': [
                {'slug': slug, 'published_at': pub.isoformat() if pub else None}
                for slug, pub in posts
            ]
        })
