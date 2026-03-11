# Future Improvements

## Background Worker: Celery + Redis

When the team grows and the single-threaded worker becomes a bottleneck, migrate to a proper job queue:

### Architecture

- **Redis** as message broker (job queue)
- **Celery** as task worker (one or more worker processes)
- **Separate Docker container** for the worker (scales independently from the web app)

### Benefits over current approach

- Multiple workers can process jobs in parallel
- Better failure recovery (automatic retries, dead-letter queues)
- Horizontal scaling: add more worker containers as needed
- Job priority support
- Built-in monitoring (Flower dashboard)

### Required changes

- Add `redis` and `celery` to requirements.txt
- Add Redis container to Docker Compose / Coolify
- Add Celery worker container (same codebase, different entrypoint)
- Replace `services/worker.py` thread with Celery tasks
- `services/database.py` stays the same (SQLite or migrate to PostgreSQL for concurrent writes)

### When to migrate

- Multiple users frequently submitting jobs simultaneously
- Single worker can't keep up with job volume
- Need for job prioritization or parallel processing
