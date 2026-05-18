from __future__ import annotations

from app.api._audio_directive import classify_directive


def test_no_actions_returns_fallback_tts():
    d = classify_directive(actions=[], reply="Algoritma adalah serangkaian langkah.")
    assert d.audio_code == "fallback_tts"
    assert d.face == "thinking"
    assert d.fetch_url is None
    assert d.screen_text and d.screen_text.startswith("Algoritma")


def test_successful_expense_returns_ok_expense():
    d = classify_directive(
        actions=[{"success": True, "type": "expense", "id": "x"}],
        reply="Pengeluaran sudah dicatat.",
    )
    assert d.audio_code == "ok_expense"
    assert d.face == "happy"


def test_successful_task_returns_ok_task():
    d = classify_directive(
        actions=[{"success": True, "type": "task", "id": "x"}],
        reply="Tugas dicatat.",
    )
    assert d.audio_code == "ok_task"
    assert d.face == "happy"


def test_successful_reminder_returns_ok_reminder():
    d = classify_directive(
        actions=[{"success": True, "type": "reminder", "id": "x"}],
        reply="Pengingat dipasang.",
    )
    assert d.audio_code == "ok_reminder"
    assert d.face == "happy"


def test_successful_summary_returns_ok_summary():
    d = classify_directive(
        actions=[{"success": True, "type": "summary"}],
        reply="Hari ini ada 3 tugas.",
    )
    assert d.audio_code == "ok_summary"
    assert d.face == "neutral"


def test_failed_action_returns_err_generic():
    d = classify_directive(
        actions=[{"success": False, "type": "expense", "error": "bad"}],
        reply="Maaf, gagal.",
    )
    assert d.audio_code == "err_generic"
    assert d.face == "sad"


def test_mixed_failure_then_success_returns_err_generic():
    d = classify_directive(
        actions=[
            {"success": False, "type": "task", "error": "x"},
            {"success": True, "type": "expense"},
        ],
        reply="Sebagian berhasil.",
    )
    assert d.audio_code == "err_generic"


def test_unknown_action_type_returns_ok_generic():
    d = classify_directive(
        actions=[{"success": True, "type": "device_command"}],
        reply="OK.",
    )
    assert d.audio_code == "ok_generic"
    assert d.face == "happy"


def test_screen_text_truncated_with_ellipsis():
    long_reply = "Ini adalah respons yang sangat panjang " * 10
    d = classify_directive(
        actions=[{"success": True, "type": "task"}],
        reply=long_reply,
    )
    assert d.screen_text is not None
    assert len(d.screen_text) <= 60
    assert d.screen_text.endswith("\u2026")


def test_screen_text_collapses_whitespace():
    d = classify_directive(
        actions=[{"success": True, "type": "expense"}],
        reply="Halo\n\n  dunia\t\tlagi",
    )
    assert d.screen_text == "Halo dunia lagi"


def test_fetch_url_always_null_in_phase_10():
    d_fallback = classify_directive(actions=[], reply="x")
    d_success = classify_directive(
        actions=[{"success": True, "type": "task"}], reply="x"
    )
    d_error = classify_directive(
        actions=[{"success": False, "type": "task"}], reply="x"
    )
    assert d_fallback.fetch_url is None
    assert d_success.fetch_url is None
    assert d_error.fetch_url is None
