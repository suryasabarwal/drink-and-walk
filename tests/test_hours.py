import pytest
from dw.hours import parse

FRI, SAT, MON = 4, 5, 0


def h(m, hh=0):
    return m * 60 + hh


def test_overnight_range_carries_into_next_morning():
    x = parse("Mo-Fr 16:00-02:00; Sa,Su 12:00-02:00")
    assert x.is_open(FRI, h(17)) is True
    assert x.is_open(FRI, h(25)) is True      # 1am Saturday, still Friday's hours
    assert x.is_open(FRI, h(27)) is False     # 3am
    assert x.is_open(MON, h(10)) is False


def test_carryover_seen_from_the_next_day():
    x = parse("Fr 18:00-03:00")
    assert x.is_open(SAT, h(1)) is True
    assert x.is_open(SAT, h(4)) is False


def test_24_7():
    assert parse("24/7").is_open(3, 5) is True


def test_midnight_close_is_not_open_after():
    x = parse("Su 12:00-00:00")
    assert x.is_open(6, h(23)) is True
    assert x.is_open(0, h(0, 30)) is False


def test_multiple_ranges_and_off():
    x = parse("Mo,We 10:00-12:00,14:00-18:00; We off")
    assert x.is_open(0, h(11)) is True and x.is_open(0, h(13)) is False
    assert x.is_open(2, h(11)) is False


@pytest.mark.parametrize("bad", ["", None, "sunrise-sunset", "Mo-Fr 10:00-18:00; PH 12:00-14:00", "by appointment", "Mo-Fr 25:00-26:00", "Mo[1] 10:00-12:00"])
def test_unreadable_is_unknown_not_a_guess(bad):
    assert parse(bad).known is False and parse(bad).is_open(1, 600) is None


def test_ph_off_is_ignored():
    assert parse("Mo-Fr 09:00-17:00; PH off").is_open(1, h(10)) is True


def test_holiday_token_in_a_day_list_keeps_the_plain_days():
    x = parse("Mo-Sa 11:00-22:00; Su,PH 12:00-21:00")
    assert x.known and x.is_open(6, h(20)) is True and x.is_open(6, h(21, 30)) is False


def test_colon_after_days_and_spaced_ranges():
    assert parse("Mo-Fr: 11:00-22:00").is_open(FRI, h(21)) is True
    assert parse("Mo - Fr 11:00-22:00").is_open(MON, h(12)) is True
