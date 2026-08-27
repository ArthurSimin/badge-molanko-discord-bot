#!/usr/bin/env node
const { MiQ } = require('makeitaquote');

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

(async () => {
  try {
    const miq = new MiQ();

    if (options.text != null) miq.setText(String(options.text));
    if (options.avatar) miq.setAvatar(options.avatar);
    if (options.username) miq.setUsername(String(options.username));
    if (options.displayName) miq.setDisplayName(String(options.displayName));
    if (options.theme) miq.setTheme(options.theme);

    const png = await miq.toBuffer('png');
    process.stdout.write(png);
  } catch (err) {
    console.error(err && err.message ? err.message : String(err));
    process.exit(1);
  }
})();
