from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))

import capture


def test_save_url_to_karakeep_skips_note_list_and_tags_for_existing_bookmark(monkeypatch):
    calls = []

    def fake_run_json(cmd):
        calls.append(cmd)
        if cmd[2] == 'save-url':
            return True, {'id': 'bm-existing', 'alreadyExists': True}, ''
        raise AssertionError(f'unexpected command: {cmd}')

    monkeypatch.setattr(capture, 'run_json', fake_run_json)

    bookmark_id, already_exists = capture.save_url_to_karakeep(
        'https://example.com',
        'https://example.com - Example',
        'triage',
    )

    assert bookmark_id == 'bm-existing'
    assert already_exists is True
    invoked = [' '.join(cmd[2:4]) for cmd in calls]
    assert invoked == ['save-url https://example.com']


def test_process_line_skips_duplicate_task_when_karakeep_reuses_bookmark(monkeypatch, capsys):
    add_task_calls = []

    monkeypatch.setattr(capture, 'extract_urls', lambda text: ['https://example.com'])
    monkeypatch.setattr(
        capture,
        'save_url_to_karakeep',
        lambda url, line, area: ('bm-123', True),
    )
    monkeypatch.setattr(
        capture,
        'add_task',
        lambda text, area, priority, note, note_meta=None: add_task_calls.append(
            (text, area, priority, note, note_meta)
        ) or True,
    )

    ok = capture.process_line(
        'https://example.com - Example',
        area_override='triage',
        priority='low',
        note=None,
        karakeep_enabled=True,
    )

    assert ok is True
    assert add_task_calls == []
    out = capsys.readouterr().out
    assert 'task duplicada não será criada' in out
    assert 'bm-123' in out


def test_process_line_multiple_urls_creates_one_task_and_backfills_existing_refs(monkeypatch):
    add_task_calls = []
    attached = []

    monkeypatch.setattr(
        capture,
        'extract_urls',
        lambda text: ['https://old.example.com', 'https://new.example.com'],
    )

    def fake_save(url, line, area):
        if 'old.' in url:
            return 'bm-old', True
        return 'bm-new', False

    monkeypatch.setattr(capture, 'save_url_to_karakeep', fake_save)
    monkeypatch.setattr(capture, 'attach_task_ref_to_bookmark', lambda bookmark_id, task_ref: attached.append((bookmark_id, task_ref)))
    monkeypatch.setattr(
        capture,
        'add_task',
        lambda text, area, priority, note, note_meta=None: add_task_calls.append(
            (text, area, priority, note, note_meta)
        ) or True,
    )

    ok = capture.process_line(
        'old https://old.example.com new https://new.example.com',
        area_override='triage',
        priority='low',
        note=None,
        karakeep_enabled=True,
    )

    assert ok is True
    assert add_task_calls == [
        (
            'old https://old.example.com new https://new.example.com',
            'triage',
            'low',
            None,
            ['karakeep:bm-old', 'karakeep:bm-new'],
        )
    ]
    assert attached == [
        ('bm-old', 'task-ref: Work Tasks.md#old-new')
    ]


def test_process_line_creates_task_for_new_bookmark(monkeypatch):
    add_task_calls = []

    monkeypatch.setattr(capture, 'extract_urls', lambda text: ['https://example.com'])
    monkeypatch.setattr(
        capture,
        'save_url_to_karakeep',
        lambda url, line, area: ('bm-456', False),
    )
    monkeypatch.setattr(
        capture,
        'add_task',
        lambda text, area, priority, note, note_meta=None: add_task_calls.append(
            (text, area, priority, note, note_meta)
        ) or True,
    )

    ok = capture.process_line(
        'https://example.com - Example',
        area_override='triage',
        priority='low',
        note=None,
        karakeep_enabled=True,
    )

    assert ok is True
    assert add_task_calls == [
        (
            'https://example.com - Example',
            'triage',
            'low',
            None,
            ['karakeep:bm-456'],
        )
    ]
