from django.urls import path

from apps.blog.public_views import (
    PublicBlogPostListView,
    PublicBlogPostDetailView,
    PublicBlogCategoryListView,
    PublicBlogPostPreviewView,
    PublicBlogSitemapView,
)

urlpatterns = [
    path('posts/', PublicBlogPostListView.as_view(), name='public-blog-posts'),
    path('posts/<slug:slug>/', PublicBlogPostDetailView.as_view(), name='public-blog-post-detail'),
    path('categories/', PublicBlogCategoryListView.as_view(), name='public-blog-categories'),
    path('preview/<str:post_id>/', PublicBlogPostPreviewView.as_view(), name='public-blog-preview'),
    path('sitemap/', PublicBlogSitemapView.as_view(), name='public-blog-sitemap'),
]
