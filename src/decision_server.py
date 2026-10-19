"""在本机提供决策页面，并在网页关闭后继续按小时检查天气。"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

from .decision_build import build
from .decision_weather import LOCATIONS, get_weather
from .live_data import read_cached
from .weather_worker import update_all


class WeatherService:
    def __init__(self, root: Path, interval: int = 3600):
        self.root = Path(root).resolve()
        self.interval = interval
        self.stop = threading.Event()
        self.state = {'running': False, 'interval_seconds': interval, 'last_started_at_utc': None, 'last_finished_at_utc': None, 'errors': []}
        self.thread = threading.Thread(target=self.run, daemon=True, name='weather-hourly')

    def run(self):
        self.state['running'] = True
        try:
            while not self.stop.is_set():
                self.state['last_started_at_utc'] = datetime.now(timezone.utc).isoformat()
                try:
                    report = update_all(self.root)
                    self.state['errors'] = report.get('errors', [])
                except Exception as exc:
                    self.state['errors'] = [{'error': str(exc)}]
                self.state['last_finished_at_utc'] = datetime.now(timezone.utc).isoformat()
                (self.root / 'runtime').mkdir(exist_ok=True)
                (self.root / 'runtime/server_status.json').write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding='utf-8')
                if self.stop.wait(self.interval):
                    break
        finally:
            self.state['running'] = False


def reference_status(root: Path, key: str) -> dict:
    products = {}
    descriptions = []
    for product, label in [('station', '站点参考'), ('archive', 'ERA5背景')]:
        result = read_cached(root, key, product)
        snapshot = result.get('snapshot')
        if snapshot:
            coverage = snapshot['coverage']
            latest = coverage.get('latest_available_date') or '无完整日期'
            descriptions.append(f"{label}：{coverage['complete_day_count']}/{coverage['expected_day_count']}日完整，末次有效{latest}" + ('（已过期）' if result['status'] == 'stale_cache' else ''))
            products[product] = {'status': result['status'], 'fetched_at_utc': snapshot['fetched_at_utc'], 'coverage': coverage, 'error': result.get('error')}
        else:
            descriptions.append(f'{label}：尚无有效缓存')
            products[product] = {'status': result['status'], 'error': result.get('error')}
    return {'location_key': key, 'products': products, 'summary': '；'.join(descriptions) + '。后台按日核查，缺失不补零；新增记录不改写冻结实验。'}


def make_handler(root: Path, service: WeatherService):
    class Handler(BaseHTTPRequestHandler):
        def send_data(self, code, content, mime):
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def send_json(self, code, data):
            self.send_data(code, json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8'), 'application/json; charset=utf-8')

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == '/favicon.ico':
                self.send_data(204, b'', 'image/x-icon')
                return
            if parsed.path in {'/', '/index.html', '/demo.html'}:
                filename = 'demo.html' if parsed.path == '/demo.html' else 'index.html'
                path = root / filename
                if not path.is_file():
                    self.send_json(404, {'error': '页面尚未构建。'})
                else:
                    self.send_data(200, path.read_bytes(), 'text/html; charset=utf-8')
                return
            if parsed.path == '/api/health':
                self.send_json(200, {'status': 'ok', 'worker': service.state})
                return
            key = query.get('location', ['hangzhou'])[0]
            if key not in LOCATIONS:
                self.send_json(400, {'error': '未知天气参考点。'})
                return
            try:
                if parsed.path == '/api/decision-weather':
                    self.send_json(200, get_weather(root, key, refresh=True, force=query.get('force') == ['1']))
                elif parsed.path == '/api/reference-status':
                    self.send_json(200, reference_status(root, key))
                else:
                    self.send_json(404, {'error': '没有这个入口。'})
            except Exception as exc:
                self.send_json(503, {'error': '数据服务暂不可用：' + str(exc)})

        def log_message(self, format, *args):
            # 仅保留请求路径和状态，不记录个人成本；成本始终在浏览器内计算。
            print('[本机服务] ' + format % args, flush=True)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--port', type=int, default=8532)
    parser.add_argument('--no-worker', action='store_true', help='仅供隔离测试，关闭后台更新')
    args = parser.parse_args()
    root = args.root.resolve()
    build(root)
    service = WeatherService(root)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(root, service))
    if not args.no_worker:
        service.thread.start()
    print(f'梅雨有数已启动：http://127.0.0.1:{args.port}/', flush=True)
    print('服务保持运行时会按小时检查天气。按Ctrl+C停止。', flush=True)
    try:
        server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:
        pass
    finally:
        service.stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
