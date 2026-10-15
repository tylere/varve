from varve.timestamp import ts_slug


def test_readable_iso_like_format():
    assert ts_slug("2026-10-06T22:07:53Z") == "2026-10-06T22-07-53Z"


def test_utc_offset_and_fraction():
    assert ts_slug("2026-10-06T22:07:53.123456+00:00") == "2026-10-06T22-07-53Z"


def test_converts_to_utc():
    assert ts_slug("2026-10-06T16:07:53-06:00") == "2026-10-06T22-07-53Z"


def test_sorts_chronologically_as_text():
    times = ["2026-10-06T22:07:53Z", "2026-10-06T09:00:00Z", "2026-12-31T23:59:59Z", "2027-01-01T00:00:00Z"]
    assert sorted(ts_slug(t) for t in times) == [ts_slug(t) for t in sorted(times)]
