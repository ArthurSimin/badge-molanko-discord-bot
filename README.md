# Molanko Discord Bot

```bash
git clone --depth 1 --branch main https://github.com/lanlan3292/molanko-discord-bot.git
cd molanko-discord-bot
mv cogs/screenshot_web.py cogs/screenshot_web.py.disabled
```

```bash
python -m venv .venv
source .venv/Scripts/activate

python -m pip install -r requirements.txt

npm ci
```

```bash
python main.py
```
