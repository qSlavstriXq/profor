"""Собирает программы вузов с ucheba.ru в формат admissions/data/<code>.json.

    python tools/scrape_ucheba.py              # все вузы из UNIVERSITIES
    python tools/scrape_ucheba.py hse mipt     # только эти
    python tools/scrape_ucheba.py --fresh hse  # скачать страницы заново (новый год приёма)

После сбора загрузите данные: python manage.py load_universities
Скачанные страницы хранятся в tools/.cache, повторный запуск берёт их оттуда.
Что пропущено и почему, пишется в tools/.cache/skipped_<code>.txt.

Чтобы добавить вуз: найдите его страницу на ucheba.ru (www.ucheba.ru/uz/<номер>)
и допишите его в UNIVERSITIES. Данные агрегатора не проверены, поэтому verified=false.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent / ".cache"
OUT_DIR = Path(__file__).resolve().parent.parent / "admissions" / "data"
FRESH = False  # True: не брать страницы из кэша

SUBJECTS = {
    "mathematics": "math", "russian": "russian", "informatics": "informatics",
    "physics": "physics", "chemistry": "chemistry", "biology": "biology",
    "social": "social", "history": "history", "literature": "literature",
    "foreignlanguage": "english", "english": "english", "geography": "geography",
}
FORMS = {"очно": "full_time", "очно-заочно": "part_time", "заочно": "distance", "дистанционно": "distance"}

# uz_id: номер вуза на ucheba.ru
UNIVERSITIES = {
    "hse": dict(uz_id=5723, name="Национальный исследовательский университет «Высшая школа экономики»",
                short_name="ВШЭ", website="https://www.hse.ru", has_dormitory=True),
    "mipt": dict(uz_id=5923, name="Московский физико-технический институт (национальный исследовательский университет)",
                 short_name="МФТИ", city="Долгопрудный", website="https://mipt.ru", has_dormitory=True),
    "bmstu": dict(uz_id=6324, name="Московский государственный технический университет им. Н.Э. Баумана",
                  short_name="МГТУ им. Баумана", website="https://bmstu.ru", has_dormitory=True),
    "ranepa": dict(uz_id=5692, name="Российская академия народного хозяйства и государственной службы при Президенте РФ",
                   short_name="РАНХиГС", website="https://www.ranepa.ru", has_dormitory=True),
    "sechenov": dict(uz_id=5833, name="Первый МГМУ им. И.М. Сеченова (Сеченовский Университет)",
                     short_name="Сеченовский", website="https://www.sechenov.ru", has_dormitory=True),
}


def fetch(url):
    path = CACHE / (re.sub(r"[^\w]+", "_", url) + ".html")
    if path.exists() and not FRESH:
        return path.read_text(encoding="utf-8")
    time.sleep(1)  # не нагружаем сайт
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        text = response.read().decode("utf-8")
    path.write_text(text, encoding="utf-8")
    return text


def next_data(html):
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(match.group(1))


def list_program_ids(uz_id):
    ids, page = [], 1
    while True:
        url = f"https://www.ucheba.ru/uz/{uz_id}/programs" + (f"?page={page}" if page > 1 else "")
        block = next_data(fetch(url))["props"]["initialState"]["institutionsPrograms"]["programsHigher"]
        new = [item["id"] for item in block["items"] if item["id"] not in ids]
        ids += new
        if not new or len(ids) >= block["total"]:
            return ids, block["total"]
        page += 1


def exam(item):
    return {"subject": SUBJECTS[item["exam"]["subject"]["slug"]], "min_score": item["minPoints"] or 0}


def program_record(program_id, skipped):
    url = f"https://www.ucheba.ru/program/{program_id}"
    entity = next_data(fetch(url))["props"]["pageProps"]["initialState"]["institutionsProgramId"]["entity"]
    title = f"{entity['name']} ({program_id})"

    if entity.get("additionalExams"):
        names = ", ".join(e.get("title") or e.get("exam", {}).get("name", "?") for e in entity["additionalExams"])
        skipped.append(f"{title}: внутренние испытания ({names})")
        return None

    slugs = [e["exam"]["subject"]["slug"] for e in entity["requiredExams"] + entity["optionalExams"]]
    unknown = sorted({s for s in slugs if s not in SUBJECTS})
    if unknown:
        skipped.append(f"{title}: предметы вне нашего списка ({', '.join(unknown)})")
        return None

    forms = [f for f in entity["trainingForms"]
             if f["baseEducationType"]["name"] == "После 11 классов" and f["trainingFormType"]["name"] in FORMS]
    if not forms:
        skipped.append(f"{title}: нет очной/очно-заочной/заочной формы после 11 класса")
        return None
    form = next((f for f in forms if f["trainingFormType"]["name"] == "очно"), forms[0])

    exams = [exam(e) for e in entity["requiredExams"]]
    optional = [exam(e) for e in entity["optionalExams"]]
    if len(optional) == 1:
        exams.append(optional[0])
    elif optional:
        exams.append({"one_of": optional})

    # Больше максимума + 10 баллов за достижения: в тот год был другой набор экзаменов
    max_sum = 100 * len(exams) + 10
    stats = []
    for year in entity.get("historyYears") or []:
        stat = {"year": year["year"]}
        if year.get("examPoints") and year["examPoints"] > max_sum:
            skipped.append(f"{title}, {year['year']}: балл {year['examPoints']} больше {max_sum}, не берём")
        elif year.get("examPoints"):
            stat["passing_score_budget"] = year["examPoints"]
        if year.get("numPlaces") is not None:
            stat["budget_places"] = year["numPlaces"]
        if len(stat) > 1:
            stat["source_url"] = url
            stats.append(stat)

    record = {
        "faculty": (entity.get("faculty") or {}).get("name", "") or "",
        "name": entity["name"],
        "direction_code": entity["speciality"].get("codeOkso") or "",
        "study_form": FORMS[form["trainingFormType"]["name"]],
        "source_url": url,
        "exams": exams,
        "stats": stats,
    }
    if form.get("price"):
        record["tuition_per_year"] = form["price"]
    if entity.get("profiles"):
        record["profile"] = entity["profiles"]
    return record


def scrape(code):
    info = dict(UNIVERSITIES[code])
    uz_id = info.pop("uz_id")
    ids, total = list_program_ids(uz_id)
    skipped, programs = [], []
    for number, program_id in enumerate(ids, start=1):
        try:
            record = program_record(program_id, skipped)
        except Exception as error:  # одна сломанная страница не должна останавливать сбор
            skipped.append(f"{program_id}: ошибка разбора {error!r}")
            continue
        if record:
            programs.append(record)
        print(f"{code}: {number}/{len(ids)}", flush=True)

    # Одинаковые (факультет, название, форма) различаем профилем или номером программы
    keys = {}
    for p in programs:
        keys.setdefault((p["faculty"], p["name"], p["study_form"]), []).append(p)
    for group in keys.values():
        if len(group) > 1:
            for p in group:
                suffix = p.get("profile") or p["source_url"].rsplit("/", 1)[1]
                p["name"] = f"{p['name']} ({suffix})"
    for p in programs:
        p.pop("profile", None)

    data = {"code": code, **info,
            "source_url": f"https://www.ucheba.ru/uz/{uz_id}/programs",
            "verified": False, "programs": programs}
    out = OUT_DIR / f"{code}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = CACHE / f"skipped_{code}.txt"
    report.write_text("\n".join(skipped) + "\n", encoding="utf-8")
    print(f"{code}: всего на сайте {total}, собрано {len(ids)}, записано {len(programs)}, пропущено {len(skipped)}")


def main():
    global FRESH
    parser = argparse.ArgumentParser(description="Сбор программ вузов с ucheba.ru")
    parser.add_argument("codes", nargs="*", help=f"коды вузов: {', '.join(UNIVERSITIES)}")
    parser.add_argument("--fresh", action="store_true", help="скачать страницы заново")
    args = parser.parse_args()

    unknown = [code for code in args.codes if code not in UNIVERSITIES]
    if unknown:
        sys.exit(f"Неизвестные вузы: {', '.join(unknown)}. Есть: {', '.join(UNIVERSITIES)}")
    FRESH = args.fresh
    CACHE.mkdir(exist_ok=True)
    for code in args.codes or UNIVERSITIES:
        scrape(code)


if __name__ == "__main__":
    main()
