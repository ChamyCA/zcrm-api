from zcrm import ui


def script(monkeypatch, answers, hidden):
    answers, hidden = list(answers), list(hidden)
    monkeypatch.setattr(ui, "ask", lambda prompt, default=None: (answers.pop(0) or default))
    monkeypatch.setattr(ui, "ask_secret", lambda prompt: hidden.pop(0))
    monkeypatch.setattr(ui, "confirm", lambda prompt, default=False: True)
