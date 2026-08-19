import redis
from rq import Queue

from app.config import settings

# Shared connection
redis_conn = redis.from_url(settings.redis_url)

# Phase 4 Queues
light_queue = Queue("light", connection=redis_conn)
heavy_queue = Queue("heavy", connection=redis_conn)

# Enqueue usage for Phase 4:
# light_queue.enqueue(func, args, job_timeout="5m")
# heavy_queue.enqueue(func, args, job_timeout="2h")

# ponytail: retention scheduler deferred to Phase 6 (rq-scheduler or cron)
