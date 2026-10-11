"""Inbox poller uses EXAMINE + BODY.PEEK; never mutates mailbox."""

from __future__ import annotations

from app.mail.inbox import FORBIDDEN_IMAP, ReadOnlyIMAP


class FakeIMAP:
    def __init__(self):
        self.cmds = []

    def login(self, user, password):
        self.cmds.append("LOGIN")
        return "OK", [b"Logged in"]

    def select(self, mailbox, readonly=False):
        self.cmds.append(("SELECT", mailbox, readonly))
        return "OK", [b"1"]

    def search(self, charset, *criteria):
        self.cmds.append(("SEARCH", criteria))
        return "OK", [b"1"]

    def fetch(self, message_set, message_parts):
        self.cmds.append(("FETCH", message_parts))
        return "OK", []

    def list(self, *a, **k):
        self.cmds.append("LIST")
        return "OK", []

    def logout(self):
        self.cmds.append("LOGOUT")
        return "OK", []


def test_readonly_uses_examine_and_peek():
    fake = FakeIMAP()
    wrap = ReadOnlyIMAP(fake)  # type: ignore[arg-type]
    wrap.login("u", "p")
    wrap.examine("INBOX")
    wrap.search(None, "ALL")
    wrap.fetch("1", "(BODY.PEEK[]<0.65536>)")
    wrap.logout()
    assert "EXAMINE" in wrap.calls
    assert "FETCH" in wrap.calls
    assert "LOGIN" in wrap.calls
    # underlying select called readonly
    assert any(c[0] == "SELECT" and c[2] is True for c in fake.cmds if isinstance(c, tuple))


def test_forbidden_commands():
    wrap = ReadOnlyIMAP(FakeIMAP())  # type: ignore[arg-type]
    for name in ("store", "expunge", "copy", "move", "append", "select"):
        assert name.upper() in FORBIDDEN_IMAP or name.upper() == "SELECT"
        try:
            getattr(wrap, name)()
            raised = False
        except RuntimeError as exc:
            raised = "forbidden" in str(exc).lower()
        except AttributeError:
            raised = True
        assert raised, f"{name} should be blocked"
