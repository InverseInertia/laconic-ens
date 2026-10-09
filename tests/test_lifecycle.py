from laconic.lifecycle import GRACE, STALE, Lifecycle


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make():
    c = Clock()
    return c, Lifecycle(c)


def test_never_exits_before_first_ping():
    c, lc = make()
    c.t = 10_000
    assert not lc.should_exit()


def test_exits_after_grace_when_last_page_says_bye():
    c, lc = make()
    lc.ping("a")
    lc.bye("a")
    assert not lc.should_exit()
    c.t += GRACE
    assert lc.should_exit()


def test_reload_does_not_exit():
    c, lc = make()
    lc.ping("a")
    lc.bye("a")
    c.t += GRACE - 1
    lc.ping("b")  # the reloaded page
    c.t += GRACE * 2
    lc.ping("b")
    assert not lc.should_exit()


def test_other_open_page_keeps_it_alive():
    c, lc = make()
    lc.ping("a")
    lc.ping("b")
    lc.bye("a")
    c.t += GRACE * 3
    assert not lc.should_exit()


def test_crashed_page_expires():
    c, lc = make()
    lc.ping("a")
    c.t += STALE
    assert not lc.should_exit()  # starts the grace period
    c.t += GRACE
    assert lc.should_exit()
