"""Concurrency helpers: a semaphore per user and a cancellable download job."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Hashable, Optional

from .models import FormatChoice, MediaInfo


class JobCancelled(Exception):
    """Raised inside a running job when the user pressed «لغو»."""


class UserLocks:
    """Counts running downloads per user so nobody can flood the bot."""

    def __init__(self, limit: int = 1):
        self.limit = max(1, int(limit))
        self._active: Dict[Hashable, int] = {}

    def try_acquire(self, user_id: Hashable) -> bool:
        """Reserve a download slot for ``user_id``; ``False`` when they are full."""
        current = self._active.get(user_id, 0)
        if current >= self.limit:
            return False
        self._active[user_id] = current + 1
        return True

    def release(self, user_id: Hashable) -> None:
        current = self._active.get(user_id, 0)
        if current <= 1:
            self._active.pop(user_id, None)
        else:
            self._active[user_id] = current - 1

    def is_busy(self, user_id: Hashable) -> bool:
        return self._active.get(user_id, 0) >= self.limit

    def active_count(self, user_id: Hashable) -> int:
        return self._active.get(user_id, 0)

    @property
    def size(self) -> int:
        return len(self._active)


@dataclass
class DownloadJob:
    """A pending "pick a quality" job (or a running download)."""

    id: str
    user_id: Hashable
    chat_id: Hashable
    url: str
    info: MediaInfo
    choices: list[FormatChoice] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    message_id: Optional[int] = None
    status: str = "waiting"        # waiting | running | finished | cancelled

    @classmethod
    def new(cls, user_id: Hashable, chat_id: Hashable, url: str, info: MediaInfo,
            choices: Optional[list[FormatChoice]] = None) -> "DownloadJob":
        return cls(
            id=uuid.uuid4().hex[:10],
            user_id=user_id,
            chat_id=chat_id,
            url=url,
            info=info,
            choices=choices or [],
        )

    def cancel(self) -> None:
        self.status = "cancelled"
        self.cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def expired(self, ttl_seconds: int) -> bool:
        return (time.time() - self.created_at) > ttl_seconds


class JobStore:
    """In-memory store of pending jobs, with automatic expiration."""

    def __init__(self, ttl_seconds: int = 1800, max_jobs: int = 2000):
        self.ttl_seconds = ttl_seconds
        self.max_jobs = max_jobs
        self._jobs: Dict[str, DownloadJob] = {}

    # -- lifecycle ------------------------------------------------------
    def add(self, job: DownloadJob) -> DownloadJob:
        self.purge()
        if len(self._jobs) >= self.max_jobs:
            oldest = min(self._jobs.values(), key=lambda j: j.created_at)
            self._jobs.pop(oldest.id, None)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[DownloadJob]:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.expired(self.ttl_seconds):
            self._jobs.pop(job_id, None)
            return None
        return job

    def pop(self, job_id: str) -> Optional[DownloadJob]:
        return self._jobs.pop(job_id, None)

    def latest_for_user(self, user_id: Hashable) -> Optional[DownloadJob]:
        jobs = [j for j in self._jobs.values() if j.user_id == user_id]
        if not jobs:
            return None
        return max(jobs, key=lambda j: j.created_at)

    def purge(self) -> int:
        expired = [key for key, job in self._jobs.items() if job.expired(self.ttl_seconds)]
        for key in expired:
            self._jobs.pop(key, None)
        return len(expired)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._jobs)
