from __future__ import annotations

from celery import Celery

from src.infrastructure.config.settings import settings

celery_app = Celery(
    "class_scheduling_engine",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["src.infrastructure.messaging.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,  # One task at a time — LP problems are CPU-heavy
    result_expires=86400,          # Results kept for 24 hours
    task_routes={
        "src.infrastructure.messaging.tasks.solve_schedule_task": {
            "queue": "scheduling"
        }
    },
)
