'use strict';

const fs = require('node:fs');
const path = require('node:path');

const DISABLED_FEATURE_TO_MERGE = 'AutofillAiWalletPrivatePasses';
const FALLBACK_NODE_MODULES = 'C:/Users/kongbai/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';

function asAbsolute(value) {
  return value ? path.resolve(String(value)) : null;
}

function candidateModuleRoots() {
  const roots = [];
  if (process.env.PROMO_NODE_MODULES) roots.push(asAbsolute(process.env.PROMO_NODE_MODULES));
  roots.push(FALLBACK_NODE_MODULES);
  return [...new Set(roots.filter(Boolean))];
}

function loadPlaywright() {
  const errors = [];
  try {
    const entry = require.resolve('playwright');
    return { module: require(entry), source: entry, resolution: 'require(playwright)' };
  } catch (error) {
    errors.push({ source: 'require(playwright)', error: String(error?.message || error) });
  }

  for (const root of candidateModuleRoots()) {
    const attempts = [
      path.join(root, 'playwright'),
      root,
    ];
    for (const candidate of attempts) {
      try {
        if (!fs.existsSync(candidate)) continue;
        return { module: require(candidate), source: candidate };
      } catch (error) {
        errors.push({ source: candidate, error: String(error?.message || error) });
      }
    }
    try {
      const entry = require.resolve('playwright', { paths: [root] });
      return { module: require(entry), source: entry };
    } catch (error) {
      errors.push({ source: `require.resolve(playwright, ${root})`, error: String(error?.message || error) });
    }
  }

  const detail = errors.map(item => `${item.source}: ${item.error}`).join('\n');
  throw new Error(`找不到 Playwright。优先尝试 require(playwright)，随后尝试 PROMO_NODE_MODULES 与 Codex 运行时回退。\n${detail}`);
}

function playwrightPackageRoot(playwrightSource) {
  if (!playwrightSource) return null;
  const source = path.resolve(playwrightSource);
  let current = fs.existsSync(source) && fs.statSync(source).isFile() ? path.dirname(source) : source;
  while (current && current !== path.dirname(current)) {
    if (path.basename(current) === 'playwright') return current;
    const packageJson = path.join(current, 'package.json');
    if (fs.existsSync(packageJson)) {
      try {
        const metadata = JSON.parse(fs.readFileSync(packageJson, 'utf8'));
        if (metadata.name === 'playwright') return current;
      } catch {
        // Keep walking; the package may be loaded from an unusual runtime layout.
      }
    }
    current = path.dirname(current);
  }
  return null;
}

function readDefaultDisabledFeatures(playwrightSource) {
  const playwrightRoot = playwrightPackageRoot(playwrightSource);
  const candidates = [];
  if (playwrightRoot) {
    candidates.push(path.join(path.dirname(playwrightRoot), 'playwright-core', 'lib', 'coreBundle.js'));
    candidates.push(path.join(playwrightRoot, 'node_modules', 'playwright-core', 'lib', 'coreBundle.js'));
  }
  candidates.push(path.join(FALLBACK_NODE_MODULES, 'playwright-core', 'lib', 'coreBundle.js'));
  for (const bundlePath of [...new Set(candidates)]) {
    if (!fs.existsSync(bundlePath)) continue;
    const source = fs.readFileSync(bundlePath, 'utf8');
    const match = source.match(/disabledFeatures\s*=\s*\[([\s\S]*?)\]\.filter\(Boolean\)/);
    if (!match) continue;
    const values = [...match[1].matchAll(/['"]([^'"]+)['"]/g)].map(item => item[1]);
    if (values.length) return [...new Set(values)];
  }
  throw new Error('无法从 Playwright coreBundle 读取原始 disabledFeatures，拒绝丢弃 Playwright 默认禁用项。');
}

function buildLaunchOptions(playwrightSource) {
  const defaults = readDefaultDisabledFeatures(playwrightSource);
  const merged = [...new Set([...defaults, DISABLED_FEATURE_TO_MERGE])];
  return {
    channel: 'msedge',
    headless: true,
    ignoreDefaultArgs: [`--disable-features=${defaults.join(',')}`],
    args: [`--disable-features=${merged.join(',')}`],
    metadata: {
      preferred_channel: 'msedge',
      default_disabled_features: defaults,
      merged_disabled_features: merged,
      merged_feature: DISABLED_FEATURE_TO_MERGE,
    },
  };
}

async function launchBrowser(playwrightSource) {
  const loaded = playwrightSource ? { module: require(playwrightSource), source: playwrightSource } : loadPlaywright();
  const { chromium } = loaded.module;
  if (!chromium || typeof chromium.launch !== 'function') throw new Error('Playwright 模块缺少 chromium.launch');
  const base = buildLaunchOptions(loaded.source);
  const attempts = [];
  try {
    const browser = await chromium.launch(base);
    return { browser, launch: base, playwright_source: loaded.source, attempts };
  } catch (error) {
    attempts.push({ channel: 'msedge', error: String(error?.message || error) });
    // Edge is preferred. A bundled Chromium fallback keeps the exporter portable
    // on machines where the Edge channel is not installed.
    const fallback = { ...base };
    delete fallback.channel;
    try {
      const browser = await chromium.launch(fallback);
      return { browser, launch: fallback, playwright_source: loaded.source, attempts, fallback_used: true };
    } catch (fallbackError) {
      attempts.push({ channel: 'bundled-chromium', error: String(fallbackError?.message || fallbackError) });
      const combined = attempts.map(item => `${item.channel}: ${item.error}`).join('\n');
      throw new Error(`浏览器启动失败：\n${combined}`);
    }
  }
}

module.exports = {
  DISABLED_FEATURE_TO_MERGE,
  FALLBACK_NODE_MODULES,
  candidateModuleRoots,
  loadPlaywright,
  readDefaultDisabledFeatures,
  buildLaunchOptions,
  launchBrowser,
};
