from datetime import datetime, timedelta, timezone


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FrozenClock:
    def __init__(self, current: datetime):
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        self.current = current

    def now(self) -> datetime:
        return self.current

    def advance(self, *, minutes: int) -> None:
        self.current = self.current + timedelta(minutes=minutes)
