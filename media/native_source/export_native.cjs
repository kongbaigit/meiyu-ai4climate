'use strict';

// 原生逐帧导出器。它要求目标页面暴露 window.MEIYU_FILM，并把 Canvas
// 逐帧封装为 VideoFrame 后送入 WebCodecs VideoEncoder；不调用截图录制。
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const os = require('node:os');
let playwright;
try { playwright = require('playwright'); } catch { playwright = require(path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')); }
const { chromium } = playwright;

const WORKSPACE = path.resolve(__dirname);
const TARGET_URL = process.env.MEIYU_FILM_URL || 'http://127.0.0.1:8530/index.html';
const OUTPUT_PATH = path.resolve(process.env.MEIYU_FILM_OUTPUT || path.join(WORKSPACE, 'native_raw.h264'));
const QA_PATH = path.resolve(process.env.MEIYU_FILM_QA || path.join(WORKSPACE, 'export_check.json'));
const DURATION_OVERRIDE = process.env.MEIYU_FILM_DURATION ? Number(process.env.MEIYU_FILM_DURATION) : null;
const FFMPEG_PATH = process.env.MEIYU_FFMPEG || 'ffmpeg';

function sha256(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function readDefaultDisabledFeatures() {
  let corePath;
  try { corePath = require.resolve('playwright-core'); } catch { corePath = path.join(os.homedir(), '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright-core/index.js'); }
  const bundlePath = path.join(path.dirname(corePath), 'lib/coreBundle.js');
  const source = fs.readFileSync(bundlePath, 'utf8');
  const match = source.match(/disabledFeatures = \[([\s\S]+?)\]\.filter\(Boolean\)/);
  if (!match) throw new Error('无法从 Playwright coreBundle 读取默认 disabledFeatures');
  return [...match[1].matchAll(/^\s*"([^"]+)"/gm)].map(item => item[1]);
}

function browserLaunch() {
  const defaults = readDefaultDisabledFeatures();
  const merged = [...new Set([...defaults, 'AutofillAiWalletPrivatePasses'])];
  return {
    defaults,
    merged,
    options: {
      channel: 'msedge',
      headless: true,
      ignoreDefaultArgs: [`--disable-features=${defaults.join(',')}`],
      args: [`--disable-features=${merged.join(',')}`],
    },
  };
}

function attachMonitor(page, monitor) {
  page.on('pageerror', error => monitor.page_errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') monitor.console_errors.push(message.text());
  });
  page.on('request', request => {
    try {
      const url = new URL(request.url());
      const local = ['127.0.0.1', 'localhost', '::1'].includes(url.hostname);
      const fileLike = ['file:', 'data:', 'blob:'].includes(url.protocol);
      if (!local && !fileLike) monitor.external_requests.push({ url: request.url(), method: request.method() });
    } catch {
      monitor.external_requests.push({ url: request.url(), method: request.method() });
    }
  });
  page.on('requestfailed', request => monitor.request_failures.push({ url: request.url(), error: request.failure()?.errorText || 'unknown' }));
}

async function verifyWithFfmpeg(filePath, expected) {
  const verification = { attempted: false, path: FFMPEG_PATH, frame_count: null, dimensions: [], exit_code: null, stderr_tail: null };
  if (path.isAbsolute(FFMPEG_PATH) && !fs.existsSync(FFMPEG_PATH)) {
    verification.error = 'FFmpeg 路径不存在';
    return verification;
  }
  verification.attempted = true;
  const args = ['-hide_banner', '-loglevel', 'info', '-f', 'h264', '-i', filePath, '-vf', 'showinfo', '-f', 'null', 'NUL'];
  const run = spawnSync(FFMPEG_PATH, args, { encoding: 'utf8', timeout: 120000, maxBuffer: 16 * 1024 * 1024, windowsHide: true });
  verification.exit_code = typeof run.status === 'number' ? run.status : null;
  const stderr = `${run.stderr || ''}`;
  verification.stderr_tail = stderr.slice(-4000);
  const frames = [...stderr.matchAll(/Parsed_showinfo[^\r\n]*\bn:\s*(\d+)/g)].map(item => Number(item[1]));
  const dimensions = [...new Set([...stderr.matchAll(/\bs:\s*(\d+x\d+)/g)].map(item => item[1]))];
  verification.frame_count = frames.length ? frames.length : null;
  verification.last_frame_index = frames.length ? frames[frames.length - 1] : null;
  verification.dimensions = dimensions;
  verification.ok = verification.exit_code === 0 && verification.frame_count === expected.frame_count && dimensions.includes(`${expected.width}x${expected.height}`);
  if (!verification.ok && verification.exit_code === 0 && !frames.length) verification.error = 'FFmpeg 未在 showinfo 输出中找到帧计数';
  return verification;
}

async function waitForFilm(page) {
  await page.waitForFunction(() => {
    const f = window.MEIYU_FILM;
    if (!f || !(f.canvas instanceof HTMLCanvasElement) || typeof f.renderFrame !== 'function') return false;
    if (f.ready === false) return false;
    return true;
  }, { timeout: 60000 });
  return page.evaluate(async () => {
    const f = window.MEIYU_FILM;
    if (typeof f.pause === 'function') await Promise.resolve(f.pause());
    if (f.ready && typeof f.ready.then === 'function') await f.ready;
    const fps = Number(f.fps);
    const duration = Number(f.duration);
    if (!(f.canvas instanceof HTMLCanvasElement)) throw new Error('MEIYU_FILM.canvas 不是 HTMLCanvasElement');
    if (typeof f.renderFrame !== 'function') throw new Error('MEIYU_FILM.renderFrame 缺失');
    if (!Number.isFinite(fps) || fps <= 0) throw new Error(`MEIYU_FILM.fps 无效: ${f.fps}`);
    if (!Number.isFinite(duration) || duration <= 0) throw new Error(`MEIYU_FILM.duration 无效: ${f.duration}`);
    return { width: f.canvas.width, height: f.canvas.height, fps, duration, ready_type: typeof f.ready };
  });
}

async function encodeFilm(page, meta, duration) {
  const downloadPromise = page.waitForEvent('download', { timeout: Math.max(120000, duration * 30000) });
  const encoding = await page.evaluate(async ({ duration: requestedDuration }) => {
    const f = window.MEIYU_FILM;
    const canvas = f.canvas;
    const fps = Number(f.fps);
    const duration = requestedDuration;
    const candidates = ['avc1.640028', 'avc1.420028'];
    const support = [];
    for (const codec of candidates) {
      const config = { codec, width: canvas.width, height: canvas.height, bitrate: 8_000_000, framerate: fps, avc: { format: 'annexb' } };
      try {
        const supported = await VideoEncoder.isConfigSupported(config);
        support.push({ codec, supported: supported.supported, config: supported.config });
      } catch (error) {
        support.push({ codec, supported: false, error: String(error?.message || error) });
      }
    }
    if (!support.some(item => item.supported)) throw new Error(`没有可用的 AVC Annex-B 配置: ${JSON.stringify(support)}`);
    const frameCount = Math.ceil(duration * fps - 1e-9);
    const chunks = [];
    let selected = null;
    let configureErrors = [];
    for (const item of support.filter(item => item.supported)) {
      const config = { codec: item.config.codec, width: canvas.width, height: canvas.height, bitrate: 8_000_000, framerate: fps, avc: { format: 'annexb' } };
      try {
        const test = new VideoEncoder({ output() {}, error(error) { throw error; } });
        test.configure(config);
        test.close();
        selected = config;
        break;
      } catch (error) {
        configureErrors.push({ codec: item.codec, error: String(error?.message || error) });
      }
    }
    if (!selected) throw new Error(`候选配置 configure 均失败: ${JSON.stringify(configureErrors)}`);
    let maxQueue = 0;
    let queueWaitCount = 0;
    let keyframes = 0;
    let firstTimestamp = null;
    let lastTimestamp = null;
    let outputError = null;
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
    for (let i = 0; i < frameCount; i += 1) {
      while (encoder.encodeQueueSize >= 8) {
        queueWaitCount += 1;
        await new Promise(resolve => setTimeout(resolve, 0));
      }
      const t = i / fps;
      const rendered = f.renderFrame(t, { export: true });
      if (rendered && typeof rendered.then === 'function') await rendered;
      const timestamp = Math.round(i * 1_000_000 / fps);
      const frame = new VideoFrame(canvas, { timestamp });
      encoder.encode(frame, { keyFrame: i % keyframeEvery === 0 });
      frame.close();
      maxQueue = Math.max(maxQueue, encoder.encodeQueueSize);
    }
    await encoder.flush();
    encoder.close();
    if (outputError) throw new Error(`VideoEncoder 输出错误: ${outputError}`);
    const blob = new Blob(chunks, { type: 'video/h264' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'meiyu_native.h264';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 30000);
    return {
      width: canvas.width,
      height: canvas.height,
      fps,
      duration,
      frame_count: frameCount,
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
  }, { duration });
  const download = await downloadPromise;
  const stream = await download.createReadStream();
  const bytes = [];
  for await (const chunk of stream) bytes.push(chunk);
  return { encoding, download, bytes: Buffer.concat(bytes) };
}

async function main() {
  fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
  fs.mkdirSync(path.dirname(QA_PATH), { recursive: true });
  const launch = browserLaunch();
  const monitor = { page_errors: [], console_errors: [], external_requests: [], request_failures: [] };
  const result = {
    status: 'starting',
    started_at_utc: new Date().toISOString(),
    target_url: TARGET_URL,
    output_path: OUTPUT_PATH,
    qa_path: QA_PATH,
    requested_duration_seconds: DURATION_OVERRIDE,
    browser: { channel: 'msedge', disabled_features_merged: 'AutofillAiWalletPrivatePasses', default_disabled_feature_count: launch.defaults.length, merged_disabled_feature_count: launch.merged.length },
    encoder: 'WebCodecs VideoEncoder',
    input: 'window.MEIYU_FILM.canvas -> VideoFrame',
    screenshots_used: false,
    capture_stream_used: false,
    monitor,
  };
  let browser;
  let page;
  try {
    browser = await chromium.launch(launch.options);
    page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
    attachMonitor(page, monitor);
    const response = await page.goto(TARGET_URL, { waitUntil: 'load', timeout: 60000 });
    result.http_status = response?.status() ?? null;
    const film = await waitForFilm(page);
    const duration = DURATION_OVERRIDE === null ? film.duration : DURATION_OVERRIDE;
    if (!Number.isFinite(duration) || duration <= 0) throw new Error(`导出时长无效: ${duration}`);
    result.film = { ...film, export_duration: duration };
    const encoded = await encodeFilm(page, film, duration);
    fs.writeFileSync(OUTPUT_PATH, encoded.bytes);
    result.encoding = encoded.encoding;
    result.output = { byte_length: encoded.bytes.length, sha256: sha256(encoded.bytes), suggested_filename: encoded.download.suggestedFilename(), format: 'raw H.264 Annex-B' };
    result.ffmpeg = await verifyWithFfmpeg(OUTPUT_PATH, { width: film.width, height: film.height, frame_count: encoded.encoding.frame_count });
    if (!result.ffmpeg.ok) throw new Error('FFmpeg解码核验未通过；编码文件已保留，但不能标为通过。');
    result.status = 'ok';
  } catch (error) {
    result.status = 'error';
    result.error = String(error?.stack || error);
  } finally {
    if (page) await page.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
  }
  result.finished_at_utc = new Date().toISOString();
  fs.writeFileSync(QA_PATH, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  if (result.status !== 'ok') process.exitCode = 1;
}

main().catch(error => {
  process.stderr.write(`${error?.stack || error}\n`);
  process.exitCode = 1;
});
