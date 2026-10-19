from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from src import decision_server


def test_background_updates_repeat_and_stop_without_browser(tmp_path, monkeypatch):
    called = threading.Event()
    calls = []

    def update(root):
        calls.append(root)
        if len(calls) >= 2:
            called.set()
        return {'errors': []}

    monkeypatch.setattr(decision_server, 'update_all', update)
    service = decision_server.WeatherService(tmp_path, interval=.03)
    service.thread.start()
    assert called.wait(2), '没有网页请求时也应定时更新'
    service.stop.set()
    service.thread.join(2)
    assert not service.thread.is_alive()
    assert not service.state['running']
    assert len(calls) >= 2
    assert json.loads((tmp_path / 'runtime/server_status.json').read_text())['last_finished_at_utc']


def test_http_only_serves_page_and_fixed_api(tmp_path, monkeypatch):
    (tmp_path / 'index.html').write_text('<h1>搬货决策</h1>', encoding='utf-8')
    (tmp_path / 'private.txt').write_text('不要公开', encoding='utf-8')
    seen = []

    def weather(root, key, **kwargs):
        seen.append((key, kwargs))
        return {'status': 'missing', 'snapshot': None, 'error': None}

    monkeypatch.setattr(decision_server, 'get_weather', weather)
    service = decision_server.WeatherService(tmp_path)
    server = ThreadingHTTPServer(('127.0.0.1', 0), decision_server.make_handler(tmp_path, service))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    try:
        assert '搬货决策' in urlopen(base).read().decode('utf-8')
        assert json.loads(urlopen(base + '/api/health').read())['status'] == 'ok'
        assert json.loads(urlopen(base + '/api/decision-weather?location=ningbo&force=1').read())['snapshot'] is None
        assert seen == [('ningbo', {'refresh': True, 'force': True})]
        for url, code in [('/private.txt', 404), ('/../private.txt', 404), ('/api/decision-weather?location=unknown', 400)]:
            with pytest.raises(HTTPError) as error:
                urlopen(base + url)
            assert error.value.code == code
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
