#!/usr/bin/env node
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

function primaryFamily(stack) {
  const first = String(stack).split(',')[0].trim();
  return first || 'Noto Sans SC';
}

/** PNG signature: 89 50 4E 47 0D 0A 1A 0A */
function isValidPng(buf) {
  if (!Buffer.isBuffer(buf) || buf.length < 33) return false;
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
    } catch (_) {
      // autoFont may still fetch on demand
    }

    const miq = new MiQ();

    // Theme name as string is the documented API; font via second setTheme merge.
    const themeName =
      typeof options.theme === 'string' && options.theme
        ? options.theme
        : 'dark';

    miq.setTheme(themeName);
    miq.setTheme({
      text: { font: FONT_STACK, weight: 'bold' },
      displayName: { font: FONT_STACK },
      username: { font: FONT_STACK },
    });

    if (options.text != null) miq.setText(String(options.text));
    if (options.avatar) miq.setAvatar(options.avatar);
    if (options.username) miq.setUsername(String(options.username));
    if (options.displayName) miq.setDisplayName(String(options.displayName));

    const png = await miq.toBuffer('png');

    if (!isValidPng(png)) {
      console.error(
        `Invalid PNG output (bytes=${png && png.length != null ? png.length : 0})`
      );
      process.exit(1);
    }

    if (png.length < 200) {
      console.error(`PNG too small (${png.length} bytes), likely empty render`);
      process.exit(1);
    }

    process.stdout.write(png);
  } catch (err) {
    console.error(err && err.message ? err.message : String(err));
    process.exit(1);
  }
})();
