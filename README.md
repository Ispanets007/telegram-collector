# Telegram Collector

Інкрементний OSINT-колектор публічних Telegram-каналів.  
Збирає повідомлення за курсором (last_message_id), зберігає у SQLite у канонічному форматі `author · url · date · text`, обробляє FloodWait через exponential backoff, кешує entity-resolve для захисту від банів за обсягом.

---

## Структура проєкту

```
telegram-collector/
├── collector/
│   ├── config.py          # завантаження .env
│   ├── database.py        # SQLite: messages, cursors, entity_cache, run_log
│   ├── telegram_client.py # Telethon-клієнт + entity cache + FloodWait
│   ├── collector.py       # головний цикл збору
│   └── utils.py           # backoff, resolve-бюджет, polite_sleep
├── scripts/
│   ├── collect.py         # інкрементний збір
│   ├── backfill.py        # одноразовий добір всієї історії
│   ├── stats.py           # статистика / експорт JSONL
│   └── generate_sample_data.py  # генерація демо-даних
├── sample_data/
│   ├── messages.jsonl     # 250 прикладів у канонічному форматі
│   └── messages.csv       # те саме у CSV
├── data/                  # SQLite + сесії (у .gitignore)
├── .env.example
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## Швидкий старт

### 1. Отримати Telegram API credentials

Перейдіть на https://my.telegram.org → "API development tools", створіть застосунок.  
Отримаєте `api_id` та `api_hash`.

### 2. Налаштування

```bash
cp .env.example .env
# Відредагуйте .env: TG_API_ID, TG_API_HASH, TG_PHONE, TG_CHANNELS
```

Приклад `.env`:
```
TG_API_ID=12345678
TG_API_HASH=0123456789abcdef0123456789abcdef
TG_PHONE=+380XXXXXXXXX
TG_CHANNELS=ukrainska_pravda_fast,ukrinform_ua,suspilne_news
BATCH_SIZE=100
CHANNEL_DELAY=2.0
DB_PATH=./data/collector.db
```

### 3. Встановити залежності

```bash
pip install -r requirements.txt
```

### 4. Перший запуск (авторизація)

При першому запуску Telethon запитає код підтвердження з SMS/застосунку:

```bash
python scripts/collect.py
# → "Please enter the code you received: "
```

Сесія зберігається у `data/collector.session` — повторна авторизація не потрібна.

### 5. Інкрементний збір

```bash
# Збирає нові повідомлення з усіх каналів у .env
python scripts/collect.py

# Конкретні канали, менший batch
python scripts/collect.py --channels ukrainska_pravda_fast --batch 50
```

### 6. Backfill (добір всієї історії)

```bash
python scripts/backfill.py --channels ukrainska_pravda_fast --max 2000
```

### 7. Статистика та експорт

```bash
python scripts/stats.py
python scripts/stats.py --export sample_data/export.jsonl
```

---

## Docker

```bash
# Збірка
docker-compose build

# Збір
docker-compose run collector

# Backfill
docker-compose --profile backfill run backfill

# Статистика
docker-compose --profile stats run stats
```

---

## Канонічна модель даних

| Поле       | Тип     | Опис                                     |
|------------|---------|------------------------------------------|
| author     | TEXT    | @username або `channel:<source>`         |
| url        | TEXT    | `https://t.me/<channel>/<msg_id>` UNIQUE |
| date       | TEXT    | ISO-8601 UTC                             |
| text       | TEXT    | Текст повідомлення                       |
| media_type | TEXT    | photo / video / document / NULL          |
| source     | TEXT    | Username каналу                          |

Дедуплікація: `UNIQUE(url)` + `INSERT OR IGNORE` → ідемпотентний повторний запуск.

---

## Захист від лімітів

| Проблема              | Рішення у проєкті                                              |
|-----------------------|----------------------------------------------------------------|
| **FloodWait**         | `FloodWaitError` перехоплюється, спимо `seconds + 5`, продовжуємо |
| **Бан за resolve**    | Entity cache в SQLite + денний бюджет `RESOLVE_BUDGET_PER_DAY=60` |
| **Rate limit (429)**  | `polite_sleep` між повідомленнями + `channel_delay` між каналами |
| **Збій каналу**       | `try/except` на кожен канал — помилка логується, цикл продовжується |
| **Дублікати**         | `OR IGNORE` + cursor оновлюється лише після успішного запису   |

---

## Проксі

Для SOCKS5 через Telethon (потрібен `pip install pysocks`):

```
TG_PROXY=socks5://user:pass@127.0.0.1:1080
```
