'use strict';

// 原生逐帧导出器：Canvas -> VideoFrame -> WebCodecs VideoEncoder（H.264 Annex-B）。
// 它不调用截图、录屏或 PNG 序列编码，页面只需要提供 window.MEIYU_FILM。
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const crypto = require('node:crypto');
const { URL } = require('node:url');
const browser = require('./browser.cjs');

const DEFAULT_FPS = 30;
const DEFAULT_BITRATE = 10_000_000;
const DEFAULT_HTML_CANDIDATES = [
  path.resolve(__dirname, '..', 'preview.html'),
  path.resolve(__dirname, '..', '预览.html'),
  path.resolve(__dirname, '..', '..', 'preview.html'),
  path.resolve(__dirname, '..', '..', '预览.html'),
];

function pickDefaultHtml() {
  return DEFAULT_HTML_CANDIDATES.find(candidate => fs.existsSync(candidate)) || DEFAULT_HTML_CANDIDATES[0];
}

function usage() {
  return [
    '用法：node export_video.cjs --out <新.h264路径> --report <新.json路径> [选项]',
    '选项：--html <单文件HTML路径> [默认 source/preview.html] [--start 秒] [--duration 秒] [--bitrate 比特率]',
  ].join('\n');
}

function readOptionValue(argv, index, name) {
  if (index + 1 >= argv.length || argv[index + 1].startsWith('--')) throw new Error(`${name} 需要一个值`);
  return argv[index + 1];
}

function parseFinitePositive(value, name, allowZero = false) {
  const number = Number(value);
  if (!Number.isFinite(number) || (allowZero ? number < 0 : number <= 0)) throw new Error(`${name} 无效：${value}`);
  return number;
}

function parseArgs(argv = process.argv.slice(2)) {
  const parsed = {
    html: pickDefaultHtml(),
    out: null,
    report: null,
    start: 0,
    duration: null,
    bitrate: DEFAULT_BITRATE,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === '--help' || token === '-h') return { help: true };
    const equals = token.indexOf('=');
    const key = equals >= 0 ? token.slice(0, equals) : token;
    const inline = equals >= 0 ? token.slice(equals + 1) : null;
    let value;
    if (key === '--html' || key === '--out' || key === '--report' || key === '--start' || key === '--duration' || key === '--bitrate') {
      value = inline !== null ? inline : readOptionValue(argv, i, key);
      if (inline === null) i += 1;
    } else {
      throw new Error(`未知参数：${token}`);
    }
    if (key === '--html') parsed.html = path.resolve(value);
    if (key === '--out') parsed.out = path.resolve(value);
    if (key === '--report') parsed.report = path.resolve(value);
    if (key === '--start') parsed.start = parseFinitePositive(value, '--start', true);
    if (key === '--duration') parsed.duration = parseFinitePositive(value, '--duration');
    if (key === '--bitrate') parsed.bitrate = parseFinitePositive(value, '--bitrate');
  }
  if (!parsed.out) throw new Error('必须显式提供 --out，工具不会推断或覆盖输出文件');
  if (!parsed.report) throw new Error('必须显式提供 --report，工具不会推断或覆盖报告文件');
  if (parsed.out === parsed.report) throw new Error('--out 与 --report 不能指向同一个文件');
  return parsed;
}

function assertNewPath(filePath, label) {
  if (fs.existsSync(filePath)) throw new Error(`${label} 已存在，禁止覆盖：${filePath}`);
}

function ensureHtmlFile(filePath) {
  if (!fs.existsSync(filePath)) throw new Error(`HTML 文件不存在：${filePath}`);
  if (!fs.statSync(filePath).isFile()) throw new Error(`HTML 路径不是文件：${filePath}`);
  return fs.realpathSync(filePath);
}

function sha256(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function pathInside(root, candidate) {
  const rootWithSeparator = root.endsWith(path.sep) ? root : `${root}${path.sep}`;
  return candidate === root || candidate.startsWith(rootWithSeparator);
}

function contentType(filePath) {
  const extension = path.extname(filePath).toLowerCase();
  return ({
    '.html': 'text/html; charset=utf-8',
    '.htm': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
    '.wav': 'audio/wav',
    '.mp3': 'audio/mpeg',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
  })[extension] || 'application/octet-stream';
}

function createStaticServer(htmlPath) {
  const root = fs.realpathSync(path.dirname(htmlPath));
  const basename = path.basename(htmlPath);
  const server = http.createServer((request, response) => {
    if (!['GET', 'HEAD'].includes(request.method)) {
      response.writeHead(405, { 'Allow': 'GET, HEAD' });
      response.end();
      return;
    }
    let decodedPath;
    try {
      decodedPath = decodeURIComponent(new URL(request.url || '/', 'http://127.0.0.1').pathname);
    } catch {
      response.writeHead(400);
      response.end('Bad Request');
      return;
    }
    if (decodedPath.includes('\0') || decodedPath.includes('\\')) {
      response.writeHead(403);
      response.end('Forbidden');
      return;
    }
    const relative = decodedPath.replace(/^\/+/, '') || basename;
    const candidate = path.resolve(root, relative);
    if (!pathInside(root, candidate) || !fs.existsSync(candidate)) {
      response.writeHead(404);
      response.end('Not Found');
      return;
    }
    let target;
    try {
      target = fs.realpathSync(candidate);
    } catch {
      response.writeHead(404);
      response.end('Not Found');
      return;
    }
    if (!pathInside(root, target) || !fs.statSync(target).isFile()) {
      response.writeHead(403);
      response.end('Forbidden');
      return;
    }
    const stats = fs.statSync(target);
    response.writeHead(200, {
      'Content-Type': contentType(target),
      'Content-Length': stats.size,
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    });
    if (request.method === 'HEAD') response.end();
    else fs.createReadStream(target).on('error', () => response.destroy()).pipe(response);
  });
  const ready = new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      server.removeListener('error', reject);
      const address = server.address();
      resolve({ port: address.port, root, url: `http://127.0.0.1:${address.port}/${encodeURIComponent(basename)}` });
    });
  });
  const close = () => new Promise(resolve => {
    if (!server.listening) {
      resolve();
      return;
    }
    server.close(() => resolve());
  });
  return { server, ready, close, root };
}

function attachMonitor(page, monitor) {
  page.on('pageerror', error => {
    const item = { type: 'pageerror', message: String(error?.message || error) };
    monitor.browser_errors.push(item);
    monitor.page_errors.push(item.message);
  });
  page.on('console', message => {
    if (message.type() !== 'error') return;
    const item = { type: 'console', message: message.text() };
    monitor.browser_errors.push(item);
    monitor.console_errors.push(item.message);
  });
  page.on('requestfailed', request => {
    const item = { url: request.url(), error: request.failure()?.errorText || 'unknown' };
    monitor.browser_errors.push({ type: 'requestfailed', ...item });
    monitor.request_failures.push(item);
  });
}

async function waitForFilm(page) {
  await page.waitForFunction(() => {
    const film = window.MEIYU_FILM;
    return Boolean(film && film.canvas instanceof HTMLCanvasElement && typeof film.renderFrame === 'function' && film.ready !== false);
  }, { timeout: 60_000 });
  return page.evaluate(async () => {
    const film = window.MEIYU_FILM;
    if (typeof film.pause === 'function') await Promise.resolve(film.pause());
    if (film.ready && typeof film.ready.then === 'function') await film.ready;
    const fps = Number(film.fps);
    const duration = Number(film.duration);
    if (!(film.canvas instanceof HTMLCanvasElement)) throw new Error('MEIYU_FILM.canvas 不是 HTMLCanvasElement');
    if (typeof film.renderFrame !== 'function') throw new Error('MEIYU_FILM.renderFrame 缺失');
    if (!Number.isFinite(fps) || fps <= 0) throw new Error(`MEIYU_FILM.fps 无效：${film.fps}`);
    if (!Number.isFinite(duration) || duration <= 0) throw new Error(`MEIYU_FILM.duration 无效：${film.duration}`);
    return { width: film.canvas.width, height: film.canvas.height, fps, duration, ready_type: typeof film.ready };
  });
}

async function encodeFilm(page, film, options) {
  const downloadPromise = page.waitForEvent('download', { timeout: Math.max(120_000, options.duration * 30_000) });
  const encoding = await page.evaluate(async ({ start, duration, bitrate }) => {
    const film = window.MEIYU_FILM;
    const canvas = film.canvas;
    const fps = Number(film.fps);
    const candidates = ['avc1.640028', 'avc1.4d4028', 'avc1.420028'];
    const support = [];
    for (const codec of candidates) {
      const requested = { codec, width: canvas.width, height: canvas.height, bitrate, framerate: fps, avc: { format: 'annexb' } };
      try {
        const result = await VideoEncoder.isConfigSupported(requested);
        const supported = Boolean(result && result.supported);
        support.push({ codec, supported, config: result?.config || null, requested });
      } catch (error) {
        support.push({ codec, supported: false, config: null, requested, error: String(error?.message || error) });
      }
    }
    const supportedCandidates = support.filter(item => item.supported);
    if (!supportedCandidates.length) throw new Error(`没有可用的 AVC Annex-B 配置：${JSON.stringify(support)}`);
    const configureErrors = [];
    let selected = null;
    for (const candidate of supportedCandidates) {
      const config = { ...candidate.requested, ...(candidate.config || {}), avc: { format: 'annexb' } };
      let probe = null;
      let probeError = null;
      try {
        probe = new VideoEncoder({ output() {}, error(error) { probeError = String(error?.message || error); } });
        probe.configure(config);
        if (probeError) throw new Error(probeError);
        selected = config;
        probe.close();
        break;
      } catch (error) {
        configureErrors.push({ codec: config.codec, error: String(error?.message || error) });
        if (probe) probe.close();
      }
    }
    if (!selected) throw new Error(`VideoEncoder.configure 均失败：${JSON.stringify(configureErrors)}`);

    const frameCount = Math.max(1, Math.ceil(duration * fps - 1e-9));
    const chunks = [];
    let keyframes = 0;
    let firstTimestamp = null;
    let lastTimestamp = null;
    let outputError = null;
    let maxQueue = 0;
    let queueWaitCount = 0;
    const encoder = new VideoEncoder({
      output(chunk) {
        const bytes = new Uint8Array(chunk.byteLength);
        chunk.copyTo(bytes);
        chunks.push(bytes);
        if (chunk.type === 'key') keyframes += 1;
        firstTimestamp = firstTimestamp === null ? chunk.timestamp : Math.min(firstTimestamp, chunk.timestamp);
        lastTimestamp = lastTimestamp === null ? chunk.timestamp : Math.max(lastTimestamp, chunk.timestamp);
      },
      error(error) { outputError = String(error?.message || error); },
    });
    encoder.configure(selected);
    const keyframeEvery = Math.max(1, Math.round(fps * 2));
    for (let index = 0; index < frameCount; index += 1) {
      while (encoder.encodeQueueSize >= 8) {
        queueWaitCount += 1;
        await new Promise(resolve => setTimeout(resolve, 0));
      }
      const sourceTime = start + index / fps;
      const rendered = film.renderFrame(sourceTime, { export: true });
      if (rendered && typeof rendered.then === 'function') await rendered;
      const timestamp = Math.round(index * 1_000_000 / fps);
      const frame = new VideoFrame(canvas, { timestamp });
      try {
        encoder.encode(frame, { keyFrame: index % keyframeEvery === 0 });
      } finally {
        frame.close();
      }
      maxQueue = Math.max(maxQueue, encoder.encodeQueueSize);
    }
    await encoder.flush();
    encoder.close();
    if (outputError) throw new Error(`VideoEncoder 输出错误：${outputError}`);
    if (!chunks.length) throw new Error('VideoEncoder 未输出任何 H.264 chunk');
    const blob = new Blob(chunks, { type: 'video/h264' });
    const anchor = document.createElement('a');
    anchor.href = URL.createObjectURL(blob);
    anchor.download = 'meiyu_export.h264';
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(anchor.href), 30_000);
    return {
      width: canvas.width,
      height: canvas.height,
      fps,
      start_seconds: start,
      duration_seconds: duration,
      frame_count: frameCount,
      first_source_time_seconds: start,
      last_source_time_seconds: start + (frameCount - 1) / fps,
      support,
      selected_config: selected,
      configure_errors: configureErrors,
      chunks_count: chunks.length,
      keyframes,
      first_timestamp_us: firstTimestamp,
      last_timestamp_us: lastTimestamp,
      byte_length: blob.size,
      max_encode_queue_size: maxQueue,
      queue_wait_count: queueWaitCount,
    };
  }, { start: options.start, duration: options.duration, bitrate: options.bitrate });
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const chunks = [];
  for await (const chunk of stream) chunks.push(chunk);
  return { encoding, download, bytes: Buffer.concat(chunks) };
}

function baseReport(args) {
  return {
    status: 'starting',
    started_at_utc: new Date().toISOString(),
    config: {
      html_path: args.html,
      output_path: args.out,
      report_path: args.report,
      start_seconds: args.start,
      duration_seconds: args.duration,
      bitrate: args.bitrate,
    },
    encoder: 'WebCodecs VideoEncoder',
    input: 'window.MEIYU_FILM.canvas -> VideoFrame',
    output_format: 'raw H.264 Annex-B',
    screenshots_used: false,
    capture_stream_used: false,
    browser_errors: [],
    monitor: { browser_errors: [], page_errors: [], console_errors: [], request_failures: [] },
  };
}

function writeNewFile(filePath, contents, encoding) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, contents, { encoding, flag: 'wx' });
}

async function main(argv = process.argv.slice(2)) {
  let args;
  try {
    args = parseArgs(argv);
  } catch (error) {
    process.stderr.write(`${error.message}\n${usage()}\n`);
    process.exitCode = 2;
    return null;
  }
  if (args.help) {
    process.stdout.write(`${usage()}\n`);
    return null;
  }

  const report = baseReport(args);
  let server;
  let launched;
  let page;
  try {
    assertNewPath(args.out, '--out');
    assertNewPath(args.report, '--report');
    const htmlPath = ensureHtmlFile(args.html);
    server = createStaticServer(htmlPath);
    const local = await server.ready;
    report.config.html_path = htmlPath;
    report.config.server_root = local.root;
    report.config.server_url = local.url;
    launched = await browser.launchBrowser();
    report.browser = {
      playwright_source: launched.playwright_source,
      channel: launched.launch.channel || 'bundled-chromium',
      fallback_used: Boolean(launched.fallback_used),
      launch_attempts: launched.attempts,
      disabled_features: launched.launch.metadata,
    };
    page = await launched.browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    attachMonitor(page, report.monitor);
    const response = await page.goto(local.url, { waitUntil: 'load', timeout: 60_000 });
    report.http_status = response?.status() ?? null;
    const film = await waitForFilm(page);
    if (args.start >= film.duration) throw new Error(`--start 必须小于影片时长 ${film.duration} 秒`);
    const duration = args.duration === null ? film.duration - args.start : args.duration;
    if (!(duration > 0) || args.start + duration > film.duration + 1e-9) throw new Error(`导出区间超出影片时长：start=${args.start}, duration=${duration}, film=${film.duration}`);
    const actualArgs = { ...args, duration };
    report.config.duration_seconds = duration;
    report.film = { ...film, export_duration: duration };
    const encoded = await encodeFilm(page, film, actualArgs);
    writeNewFile(args.out, encoded.bytes);
    const digest = sha256(encoded.bytes);
    report.encoding = encoded.encoding;
    report.frame_count = encoded.encoding.frame_count;
    report.first_frame_time_seconds = encoded.encoding.first_source_time_seconds;
    report.last_frame_time_seconds = encoded.encoding.last_source_time_seconds;
    report.sha256 = digest;
    report.output = { path: args.out, byte_length: encoded.bytes.length, sha256: digest, format: 'raw H.264 Annex-B' };
    report.config.actual = encoded.encoding.selected_config;
    report.status = 'ok';
  } catch (error) {
    report.status = 'error';
    report.error = String(error?.stack || error);
  } finally {
    report.browser_errors = report.monitor.browser_errors;
    if (page) await page.close().catch(error => report.browser_errors.push({ type: 'page-close', message: String(error?.message || error) }));
    if (launched?.browser) await launched.browser.close().catch(error => report.browser_errors.push({ type: 'browser-close', message: String(error?.message || error) }));
    if (server) await server.close().catch(error => report.browser_errors.push({ type: 'server-close', message: String(error?.message || error) }));
  }
  report.finished_at_utc = new Date().toISOString();
  try {
    writeNewFile(args.report, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  } catch (error) {
    report.status = 'error';
    report.report_write_error = String(error?.stack || error);
    process.stderr.write(`${report.report_write_error}\n`);
  }
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (report.status !== 'ok') process.exitCode = 1;
  return report;
}

if (require.main === module) main().catch(error => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});

module.exports = {
  DEFAULT_BITRATE,
  DEFAULT_FPS,
  DEFAULT_HTML_CANDIDATES,
  parseArgs,
  createStaticServer,
  waitForFilm,
  encodeFilm,
  main,
};
