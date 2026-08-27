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

// Primary family is first in the stack; used for prefetch.
const FONT_STACK =
  options.font ||
  'Noto Sans SC, Noto Sans TC, Noto Sans JP, sans-serif';

function primaryFamily(stack) {
  const first = String(stack).split(',')[0].trim();
  return first || 'Noto Sans SC';
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

    const themeBase =
      typeof options.theme === 'string'
        ? { extends: options.theme }
        : options.theme && typeof options.theme === 'object'
          ? options.theme
          : {};

    miq.setTheme({
      ...themeBase,
      text: { ...(themeBase.text || {}), font: FONT_STACK },
      displayName: { ...(themeBase.displayName || {}), font: FONT_STACK },
      username: { ...(themeBase.username || {}), font: FONT_STACK },
    });

    if (options.text != null) miq.setText(String(options.text));
    if (options.avatar) miq.setAvatar(options.avatar);
    if (options.username) miq.setUsername(String(options.username));
    if (options.displayName) miq.setDisplayName(String(options.displayName));

    const png = await miq.toBuffer('png');
    process.stdout.write(png);
  } catch (err) {
    console.error(err && err.message ? err.message : String(err));
    process.exit(1);
  }
})();
