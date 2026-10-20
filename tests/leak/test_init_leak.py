import shutil

from conftest import SENT_CLIENT_ID, SENT_REFRESH, SENT_SECRET, SENTINELS, all_files_text
from zcrm import ui
from zcrm.lifecycle import init


def test_init_leaks_nothing(zoho, env, monkeypatch, capsys):
    (env["home"] / ".claude").mkdir()
    monkeypatch.setattr(shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: default)
    monkeypatch.setattr(ui, "ask", lambda prompt, default=None: default or "demo1")
    it = iter([SENT_CLIENT_ID, SENT_SECRET, SENT_REFRESH])
    monkeypatch.setattr(ui, "ask_secret", lambda prompt: next(it))
    assert init.run() == 0
    cap = capsys.readouterr()
    blob = cap.out + cap.err + all_files_text(env["home"]) + all_files_text(env["tmp"] / "zcrm-home")
    for s in SENTINELS:
        assert s not in blob
