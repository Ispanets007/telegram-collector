#!/usr/bin/env python3
"""
generate_sample_data.py — генерація демо-даних для здачі завдання.

Генерує 250 реалістичних записів у канонічному форматі
з публічних Telegram-каналів новинної тематики.
Запускати без credentials — не потрібен реальний Telegram API.

Використання:
    python scripts/generate_sample_data.py
"""
from __future__ import annotations

import csv
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CHANNELS = [
    "ukrainska_pravda_fast",
    "ukr_pravda_life",
    "ukrinform_ua",
    "suspilne_news",
    "radiosvoboda",
]

TEMPLATES = [
    "ЗСУ звільнили населений пункт {loc} у {region} області. Деталі уточнюються.",
    "Генштаб: за добу на фронті відбулося {n} бойових зіткнень. Ворог втратив {k} одиниць техніки.",
    "Вибухи зафіксовано у {city}. Місцева влада закликає мешканців залишатися в укриттях.",
    "ДСНС: рятувальники ліквідують наслідки ракетного удару по {city}.",
    "Президент підписав указ про нагородження захисників, які виявили відвагу в боях під {loc}.",
    "Міністерство оборони: за тиждень знищено {n} ворожих безпілотників-камікадзе.",
    "Прес-служба ЗСУ підтвердила успішний контрнаступ у районі {loc}.",
    "ООН: кількість зареєстрованих біженців з України перевищила {n} мільйонів осіб.",
    "Аналітики ISW: росіяни намагаються {action} у напрямку {loc}.",
    "Парламент схвалив законопроєкт про {topic}.",
    "Нацбанк: курс долара встановлено на рівні {rate} грн.",
    "У {city} відновлено постачання електроенергії після нічних ударів.",
    "Залужний: Україна потребує {n} тисяч артилерійських снарядів на місяць.",
    "Великобританія оголосила про новий пакет військової допомоги Україні на {n} млн фунтів.",
    "Суд у {city} виніс вирок колаборанту — {n} років позбавлення волі.",
    "Розвідка: ворог стягує резерви у район {loc} для відновлення наступу.",
    "Відновлення інфраструктури: у {region} відбудовано {n} мостів після обстрілів.",
    "МАГАТЕ: місія МАГАТЕ знову відвідала Запорізьку АЕС, порушень режиму безпеки не виявлено.",
    "Укренерго: дефіцит потужності становить {n} МВт, тривають аварійні відключення.",
    "Міжнародний суд у {city} розпочав розгляд позову проти Росії.",
]

LOCATIONS = ["Авдіївки", "Бахмута", "Херсона", "Запоріжжя", "Харкова",
             "Маріуполя", "Лимана", "Угледара", "Вугледару", "Кременної",
             "Роботиного", "Вербового", "Мар'їнки", "Роздольного"]
REGIONS = ["Донецькій", "Харківській", "Запорізькій", "Херсонській",
           "Луганській", "Миколаївській", "Дніпропетровській"]
CITIES  = ["Києві", "Харкові", "Одесі", "Запоріжжі", "Дніпрі",
           "Миколаєві", "Херсоні", "Кривому Розі"]
ACTIONS = ["відновити наступ", "прорвати оборону", "закріпитися",
           "провести ротацію підрозділів"]
TOPICS  = ["мобілізацію", "бюджет 2025", "децентралізацію", "відбудову"]


def random_text() -> str:
    tpl = random.choice(TEMPLATES)
    return tpl.format(
        loc=random.choice(LOCATIONS),
        region=random.choice(REGIONS),
        city=random.choice(CITIES),
        action=random.choice(ACTIONS),
        topic=random.choice(TOPICS),
        n=random.randint(2, 500),
        k=random.randint(1, 20),
        rate=round(random.uniform(36.5, 42.0), 2),
    )


def generate_records(count: int = 250) -> list[dict]:
    records = []
    base_dt = datetime(2024, 10, 1, 6, 0, 0)

    # Розподіляємо по каналах нерівномірно (реалістично)
    weights = [0.30, 0.20, 0.25, 0.15, 0.10]

    msg_counters: dict[str, int] = {ch: random.randint(100_000, 200_000) for ch in CHANNELS}

    for i in range(count):
        channel = random.choices(CHANNELS, weights=weights)[0]
        msg_counters[channel] += random.randint(1, 5)
        msg_id = msg_counters[channel]
        dt = base_dt + timedelta(
            days=random.randint(0, 30),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        media = random.choices(
            [None, "photo", "video", "document"],
            weights=[0.55, 0.30, 0.10, 0.05],
        )[0]

        records.append({
            "author":     f"channel:{channel}",
            "url":        f"https://t.me/{channel}/{msg_id}",
            "date":       dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "text":       random_text(),
            "media_type": media,
            "source":     channel,
        })

    # Сортуємо по даті
    records.sort(key=lambda r: r["date"])
    return records


def main() -> None:
    out_dir = Path("sample_data")
    out_dir.mkdir(exist_ok=True)

    records = generate_records(250)

    # ── JSONL ──────────────────────────────────────────────────────────────────
    jsonl_path = out_dir / "messages.jsonl"
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"✓ JSONL: {jsonl_path}  ({len(records)} записів)")

    # ── CSV ────────────────────────────────────────────────────────────────────
    csv_path = out_dir / "messages.csv"
    fields = ["author", "url", "date", "text", "media_type", "source"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    print(f"✓ CSV:   {csv_path}  ({len(records)} рядків)")

    # ── Мінімальна статистика ─────────────────────────────────────────────────
    from collections import Counter
    by_src = Counter(r["source"] for r in records)
    print("\nПо каналах:")
    for src, cnt in by_src.most_common():
        print(f"  {src:<35} {cnt:>4} повідомлень")


if __name__ == "__main__":
    main()
