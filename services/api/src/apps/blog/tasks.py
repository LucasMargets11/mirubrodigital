"""
Celery periodic task for publishing scheduled blog posts.

Added to CELERY_BEAT_SCHEDULE to run every 5 minutes.
"""
from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name='blog.publish_scheduled_posts',
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def publish_scheduled_posts(self):
    """Publish blog posts whose scheduled_publish_at has arrived."""
    from apps.blog.service import publish_scheduled_posts as do_publish

    count = do_publish()
    logger.info('blog.publish_scheduled_posts: published %d posts', count)
    return {'published': count}
