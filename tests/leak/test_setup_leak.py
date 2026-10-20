from conftest import SENT_CLIENT_ID, SENT_REFRESH, SENT_SECRET, SENTINELS, all_files_text
from helpers import script
from zcrm.lifecycle import setup


def test_sentinels_absent_from_files_and_output(zoho, monkeypatch, capsys, env):
    script(monkeypatch, [".com", "demo", "v8", ""], [SENT_CLIENT_ID, SENT_SECRET, SENT_REFRESH])
    setup.run("p1")
    captured = capsys.readouterr()
    blob = captured.out + captured.err + all_files_text(env["tmp"] / "zcrm-home") + all_files_text(env["home"])
    for sentinel in SENTINELS:
        assert sentinel not in blob
