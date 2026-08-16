from celery import Celery

from app.config import settings

celery = Celery(
    "veditor_tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_routes={
        "app.tasks.light.*": {"queue": "light"},
        "app.tasks.heavy.*": {"queue": "heavy"},
    }
)


@celery.task
def stub_task():
    return True
