#!/usr/bin/env node
/**
 * Romarr graphic-identity renderer.
 *
 * The SVG sources in ``assets/`` are the tracked source of truth
 * (text, diff-able, infinitely scalable). PNG / favicon renders are
 * build artifacts — this script regenerates them and installs the
 * web-facing ones into ``romarr/web/public/``.
 *
 * Usage:
 *   npm run assets               # render + install into web/public
 *   node scripts/render-assets.js --no-install   # render only
 *
 * Requires ONE of: rsvg-convert (librsvg), inkscape, ImageMagick
 * (magick/convert), or cairosvg. rsvg-convert is preferred.
 */

const { execSync, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const ASSETS = path.join(ROOT, 'assets');
const RENDER = path.join(ASSETS, 'render');
const WEB_PUBLIC = path.join(ROOT, 'romarr', 'web', 'public');

const install = !process.argv.includes('--no-install');

// --- pick a renderer --------------------------------------------------------
function have(bin) {
  try {
    execSync(`command -v ${bin}`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

let renderer = null;
if (have('rsvg-convert')) renderer = 'rsvg';
else if (have('inkscape')) renderer = 'inkscape';
else if (have('magick')) renderer = 'magick';
else if (have('convert')) renderer = 'convert';
else if (have('cairosvg')) renderer = 'cairosvg';

if (!renderer) {
  console.error(
    '❌ No SVG renderer found. Install one of:\n' +
    '   - librsvg     (apt install librsvg2-bin)   ← preferred\n' +
    '   - inkscape\n' +
    '   - ImageMagick (apt install imagemagick)\n' +
    '   - cairosvg    (pip install cairosvg)',
  );
  process.exit(1);
}
console.log(`🎨 Renderer: ${renderer}`);

// --- render one SVG → PNG at a given square/explicit size -------------------
function render(svg, out, width, height) {
  const h = height || width;
  fs.mkdirSync(path.dirname(out), { recursive: true });
  switch (renderer) {
    case 'rsvg':
      execFileSync('rsvg-convert', [
        '-w', String(width), '-h', String(h), svg, '-o', out,
      ]);
      break;
    case 'inkscape':
      execFileSync('inkscape', [
        svg, '--export-type=png', `--export-filename=${out}`,
        `--export-width=${width}`, `--export-height=${h}`,
      ]);
      break;
    case 'magick':
      execFileSync('magick', [
        '-background', 'none', '-density', '384',
        svg, '-resize', `${width}x${h}`, out,
      ]);
      break;
    case 'convert':
      execFileSync('convert', [
        '-background', 'none', '-density', '384',
        svg, '-resize', `${width}x${h}`, out,
      ]);
      break;
    case 'cairosvg':
      execFileSync('cairosvg', [
        svg, '-o', out,
        '--output-width', String(width), '--output-height', String(h),
      ]);
      break;
  }
  console.log(`   ✓ ${path.relative(ROOT, out)}  (${width}x${h})`);
}

// --- targets ----------------------------------------------------------------
const icon = path.join(ASSETS, 'icon.svg');
const favicon = path.join(ASSETS, 'favicon.svg');
const banner = path.join(ASSETS, 'banner.svg');

for (const f of [icon, favicon, banner]) {
  if (!fs.existsSync(f)) {
    console.error(`❌ Missing source SVG: ${path.relative(ROOT, f)}`);
    process.exit(1);
  }
}

console.log('\n📦 Rendering icon / favicon PNGs into assets/render/ ...');
render(icon, path.join(RENDER, 'icon-192.png'), 192);
render(icon, path.join(RENDER, 'icon-512.png'), 512);
// The icon is edge-to-edge (badge fills the frame) so it is already
// maskable-safe — the same source doubles as the maskable variant.
render(icon, path.join(RENDER, 'icon-512-maskable.png'), 512);
render(favicon, path.join(RENDER, 'favicon-16.png'), 16);
render(favicon, path.join(RENDER, 'favicon-32.png'), 32);
render(favicon, path.join(RENDER, 'favicon-48.png'), 48);

// The README banner is a TRACKED render (README.md references it
// directly) — written to assets/banner.png, not the gitignored
// assets/render/ dir.
console.log('\n🖼️  Rendering README banner into assets/banner.png ...');
render(banner, path.join(ASSETS, 'banner.png'), 1280, 360);

// --- install web-facing assets ---------------------------------------------
if (install) {
  console.log('\n🚚 Installing web assets into romarr/web/public/ ...');
  if (!fs.existsSync(WEB_PUBLIC)) {
    console.warn(`   ⚠️  ${path.relative(ROOT, WEB_PUBLIC)} not found — skipping install.`);
  } else {
    // Vite serves /favicon.svg straight from public/ — index.html
    // already references it.
    fs.copyFileSync(favicon, path.join(WEB_PUBLIC, 'favicon.svg'));
    console.log('   ✓ romarr/web/public/favicon.svg');
    for (const name of ['icon-192.png', 'icon-512.png', 'icon-512-maskable.png']) {
      fs.copyFileSync(path.join(RENDER, name), path.join(WEB_PUBLIC, name));
      console.log(`   ✓ romarr/web/public/${name}`);
    }
  }
} else {
  console.log('\n⏭️  --no-install: skipped copying into web/public/.');
}

console.log('\n✅ Assets rendered.');
console.log('   Sources : assets/{icon,favicon,banner}.svg  (tracked)');
console.log('   Renders : assets/render/*.png                (regenerable)');
