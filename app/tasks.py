from celery import Celery

from app.config import settings

celery_app = Celery(
    "veditor_tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_routes={
        "app.tasks.light.*": {"queue": "light"},
        "app.tasks.heavy.*": {"queue": "heavy"},
    }
)

@celery_app.task
def stub_task():
    return True
