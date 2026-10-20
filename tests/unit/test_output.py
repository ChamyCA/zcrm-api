import json

from zcrm import output
from zcrm.output import ZcrmError


def test_redacts_registered_and_patterns(capsys):
    output.register_secret("supersecretvalue123")
    output.emit_json(
        {
            "a": "x supersecretvalue123 y",
            "b": ["1000." + "ab" * 16 + "." + "cd" * 16],
            "c": "Authorization: Zoho-oauthtoken abcdefgh12345678",
            "d": 'refresh_token="abcdefghijkl"',
            "e": {"nested": "client_secret: abcdefghijkl"},
        }
    )
    out = capsys.readouterr().out
    for leaked in ("supersecretvalue123", "abcdefgh12345678", "abcdefghijkl", "ab" * 16):
        assert leaked not in out
    assert output.REDACTED in out


def test_normal_text_untouched(capsys):
    output.emit_json({"code": "SUCCESS", "id": "5725767000001234567"})
    assert json.loads(capsys.readouterr().out) == {"code": "SUCCESS", "id": "5725767000001234567"}


def test_error_envelope_and_stderr(capsys):
    output.register_secret("topsecret-token")
    err = ZcrmError("x", "bad topsecret-token", fix="do y", exit_code=5, extra="e")
    env = err.envelope()
    assert env["error"]["fix"] == "do y" and env["extra"] == "e"
    output.emit_text("note topsecret-token")
    assert "topsecret-token" not in capsys.readouterr().err
