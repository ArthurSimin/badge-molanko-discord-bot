#!/usr/bin/env node
/**
 * Quote image renderer for molanko-discord-bot.
 * Reads options JSON from argv[2], writes PNG bytes to stdout.
 * All diagnostics go to stderr so they never corrupt the image stream.
 */
const { MiQ, fonts } = require('makeitaquote');

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

/** Accept Buffer or Uint8Array; normalize to Buffer. */
function toNodeBuffer(data) {
  if (Buffer.isBuffer(data)) return data;
  if (data instanceof Uint8Array) return Buffer.from(data);
  if (data && data.buffer instanceof ArrayBuffer) {
    return Buffer.from(data.buffer, data.byteOffset || 0, data.byteLength || data.length);
  }
  return null;
}

/** PNG signature: 89 50 4E 47 0D 0A 1A 0A */
function isValidPng(buf) {
  if (!buf || buf.length < 33) return false;
  return (
    buf[0] === 0x89 &&
    buf[1] === 0x50 &&
    buf[2] === 0x4e &&
    buf[3] === 0x47 &&
    buf[4] === 0x0d &&
    buf[5] === 0x0a &&
    buf[6] === 0x1a &&
    buf[7] === 0x0a
  );
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

    // Single setTheme: preset via extends + font overrides.
    // Calling setTheme twice can drop the preset (theme appeared broken).
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
    const png = toNodeBuffer(raw);

    if (!png) {
      console.error(
        `toBuffer returned unexpected type: ${raw == null ? 'null' : typeof raw}`
      );
      process.exit(1);
    }

    if (!isValidPng(png)) {
      const head = png.subarray(0, Math.min(16, png.length));
      console.error(
        `Invalid PNG (bytes=${png.length}, head=${head.toString('hex')})`
      );
      process.exit(1);
    }

    if (png.length < 500) {
      console.error(`PNG too small (${png.length} bytes), likely empty render`);
      process.exit(1);
    }

    process.stdout.write(png);
  } catch (err) {
    console.error(err && err.stack ? err.stack : err && err.message ? err.message : String(err));
    process.exit(1);
  }
})();
