#!/usr/bin/env node
/**
 * Quote image renderer for molanko-discord-bot.
 * Reads options JSON from argv[2], writes PNG bytes to stdout.
 *
 * makeitaquote uses console.info for font-download notices; Node's
 * console.info goes to stdout and would corrupt the PNG stream.
 * We redirect log/info to stderr before loading the library path that emits them.
 */

// MUST run before any makeitaquote code can notice/warn.
const _err = console.error.bind(console);
console.log = (...args) => _err(...args);
console.info = (...args) => _err(...args);

const { MiQ, fonts } = require('makeitaquote');
const fs = require('fs');
const os = require('os');
const path = require('path');

const optionsJson = process.argv[2];
if (!optionsJson) {
  console.error('Missing options JSON');
  process.exit(1);
}

let options;
try {
  options = JSON.parse(optionsJson);
} catch (e) {
  console.error('Invalid options JSON:', e.message);
  process.exit(1);
}

const FONT_STACK =
  options.font ||
  'Noto Sans SC, Noto Sans TC, Noto Sans JP, sans-serif';

const ALLOWED_THEMES = new Set([
  'dark',
  'light',
  'color',
  'portrait',
  'portrait-light',
  'custom',
]);

function primaryFamily(stack) {
  const first = String(stack).split(',')[0].trim();
  return first || 'Noto Sans SC';
}

function toNodeBuffer(data) {
  if (Buffer.isBuffer(data)) return data;
  if (data instanceof Uint8Array) return Buffer.from(data);
  if (data && data.buffer instanceof ArrayBuffer) {
    return Buffer.from(
      data.buffer,
      data.byteOffset || 0,
      data.byteLength || data.length
    );
  }
  return null;
}

const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/** If text was mixed into the buffer, keep from first PNG signature onward. */
function extractPng(buf) {
  if (!buf || buf.length < 8) return null;
  if (buf.subarray(0, 8).equals(PNG_MAGIC)) return buf;
  const idx = buf.indexOf(PNG_MAGIC);
  if (idx < 0) return null;
  return buf.subarray(idx);
}

(async () => {
  try {
    const primary = primaryFamily(FONT_STACK);
    try {
      await fonts.use(primary, { weights: [400, 700] });
    } catch (e) {
      console.error('font prefetch warning:', e && e.message ? e.message : e);
    }

    let themeName =
      typeof options.theme === 'string' && options.theme
        ? options.theme.trim()
        : 'dark';
    if (!ALLOWED_THEMES.has(themeName)) {
      console.error(`Unknown theme "${themeName}", falling back to dark`);
      themeName = 'dark';
    }

    const miq = new MiQ().setTheme({
      extends: themeName,
      text: { font: FONT_STACK },
      displayName: { font: FONT_STACK },
      username: { font: FONT_STACK },
    });

    if (options.text != null) miq.setText(String(options.text));
    if (options.avatar) miq.setAvatar(options.avatar);
    if (options.username) miq.setUsername(String(options.username));
    if (options.displayName) miq.setDisplayName(String(options.displayName));

    const raw = await miq.toBuffer('png');
    let png = toNodeBuffer(raw);
    if (!png) {
      console.error(
        `toBuffer returned unexpected type: ${raw == null ? 'null' : typeof raw}`
      );
      process.exit(1);
    }

    png = extractPng(png);
    if (!png) {
      const head = (toNodeBuffer(raw) || Buffer.alloc(0)).subarray(0, 64);
      console.error(
        `No PNG signature in output (bytes=${raw && raw.length}, head=${head.toString('utf8').slice(0, 80)})`
      );
      process.exit(1);
    }

    if (png.length < 500) {
      console.error(`PNG too small (${png.length} bytes), likely empty render`);
      process.exit(1);
    }

    // Prefer writing via a temp file then streaming pure bytes — avoids any
    // late library chatter that might still hit stdout.
    const tmp = path.join(
      os.tmpdir(),
      `molanko-quote-${process.pid}-${Date.now()}.png`
    );
    try {
      fs.writeFileSync(tmp, png);
      const clean = fs.readFileSync(tmp);
      process.stdout.write(clean);
    } finally {
      try {
        fs.unlinkSync(tmp);
      } catch (_) {}
    }
  } catch (err) {
    console.error(
      err && err.stack
        ? err.stack
        : err && err.message
          ? err.message
          : String(err)
    );
    process.exit(1);
  }
})();
