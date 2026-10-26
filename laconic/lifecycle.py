"""Tracks open pages so the packaged app can exit once its window is closed.

Each page posts a ping every few seconds and a bye when it unloads. A page that
simply stops pinging (crash, killed browser) expires after STALE seconds; that is
long because browsers throttle timers in hidden tabs to about one a minute. A bye
is not trusted at once, since a reload also sends one, so the server waits GRACE
seconds for the page to ping again. When another launch hands its window over,
the server holds on for EXPECT seconds while that window opens."""
import time

STALE = 120.0
GRACE = 5.0
EXPECT = 60.0


class Lifecycle:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._seen = {}          # client id -> time of last ping
        self._empty_since = None  # when the last client said bye
        self.ever_seen = False
        self._hold_until = None   # set by expect()

    def ping(self, client):
        self._seen[client] = self._clock()
        self._empty_since = None
        self.ever_seen = True

    def bye(self, client):
        self._seen.pop(client, None)
        if self.ever_seen and not self._seen:
            self._empty_since = self._clock()

    def expect(self):
        """A window is on its way: do not exit before it has had EXPECT seconds to ping."""
        self._hold_until = self._clock() + EXPECT

    def should_exit(self):
        """True once every page is gone. Never true before the first ping."""
        if not self.ever_seen:
            return False
        now = self._clock()
        self._seen = {c: t for c, t in self._seen.items() if now - t < STALE}
        if not self._seen and self._empty_since is None:
            self._empty_since = now
        if self._hold_until is not None and now < self._hold_until:
            return False
        return self._empty_since is not None and now - self._empty_since >= GRACE


lifecycle = Lifecycle()
