# tgshop — bot & API

aiogram 3 bot + FastAPI backend of the Zernolist Mini App demo. See the repository README for details.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # set BOT_TOKEN
python -m tgshop --mode all   # bot (long polling) + API on :8080
pytest && ruff check . && mypy
```
