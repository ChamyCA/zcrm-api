from zcrm.lifecycle import banner


def test_plain_when_not_a_terminal():
    text = banner.logo() + banner.box("T", ["row"]) + banner.step("x", "y")
    assert "\x1b" not in text


def test_color_forced_and_box_alignment(monkeypatch):
    monkeypatch.setenv("ZCRM_COLOR", "1")
    assert "\x1b[" in banner.logo()
    lines = banner.box("Next Steps", [banner.c("colored row", 36), "plain row"]).splitlines()
    assert len({banner.vlen(line) for line in lines}) == 1


def test_logo_has_five_rows_and_fits():
    rows = banner.logo().splitlines()
    assert len(rows) == 5 and all(len(r) <= 60 for r in rows)
