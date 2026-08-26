"""RQ Worker entrypoint for VEditor.

Starts an RQ worker process listening on the specified queue(s), reading
Redis configuration from app.config.settings and eagerly importing task modules.
"""

import argparse
import sys

import redis
import redis.exceptions
from rq import Worker

# Eagerly import task modules so job code is loaded once at worker boot
# rather than re-imported per job fork (RQ performance recommendation).
import app.tasks  # noqa: F401
from app.config import settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run an RQ worker for VEditor.",
    )
    parser.add_argument(
        "queues",
        nargs="*",
        default=["light", "heavy"],
        help="Queue names to listen on (default: light heavy)",
    )
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Run in burst mode (quit after all current jobs are processed)",
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Custom worker name",
    )

    args = parser.parse_args(argv)

    queues = args.queues if args.queues else ["light", "heavy"]

    if not settings.redis_url or not settings.redis_url.strip():
        print("Error: REDIS_URL is unset.", file=sys.stderr)
        sys.exit(1)

    try:
        redis_conn = redis.from_url(settings.redis_url)
        redis_conn.ping()
    except (redis.exceptions.RedisError, ValueError) as exc:
        print(
            f"Error: Could not connect to Redis at {settings.redis_url}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    worker = Worker(queues, connection=redis_conn, name=args.name)
    worker.work(burst=args.burst)


if __name__ == "__main__":
    main()
