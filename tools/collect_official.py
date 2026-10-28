"""Собирает программы вузов с их официальных сайтов в admissions/data/<code>.json.

    python tools/collect_official.py              # все вузы
    python tools/collect_official.py hse bmstu    # только эти
    python tools/collect_official.py --fresh hse  # скачать страницы заново (новый год приёма)

После сбора загрузите данные: python manage.py load_universities

Источник каждой цифры записывается в source_url: это страница или документ самого вуза.
Скачанные файлы хранятся в tools/.cache/official, повторный запуск берёт их оттуда.
Что пропущено и почему, пишется в tools/.cache/official/skipped_<code>.txt.

Для PDF нужна библиотека pdfplumber: pip install -r requirements-tools.txt

Проходные баллы вузы публикуют вместе с индивидуальными достижениями (до 10 баллов),
поэтому наша оценка шансов по одним баллам ЕГЭ получается чуть осторожнее.
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".cache" / "official"
OUT_DIR = ROOT.parent / "admissions" / "data"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
FRESH = False  # True: не брать файлы из кэша

# Названия предметов на сайтах вузов -> коды в нашей базе
SUBJECTS = {
    "математика": "math", "математика профильная": "math", "профильная математика": "math",
    "русский язык": "russian", "информатика": "informatics", "информатика и икт": "informatics",
    "физика": "physics", "химия": "chemistry", "биология": "biology",
    "обществознание": "social", "история": "history", "литература": "literature",
    "география": "geography", "иностранный язык": "english", "английский язык": "english",
    "иностранный (английский) язык": "english",
}
# Другие иностранные языки: в нашей форме есть только английский. Если они стоят в выборе
# вместе с английским, просто не учитываем их; если без него, программу пропускаем
OTHER_LANGUAGES = {"немецкий язык", "французский язык", "испанский язык", "китайский язык"}


# ---------- Общие помощники ----------

def fetch(url, binary=False):
    """Скачивает страницу или файл, сохраняя копию в кэше."""
    name = re.sub(r"[^\w.]+", "_", urllib.parse.unquote(url))[-150:]
    path = CACHE / name
    if not path.exists() or FRESH:
        time.sleep(1)  # не нагружаем сайт вуза
        quoted = urllib.parse.quote(url, safe=":/?&=%#")
        request = urllib.request.Request(quoted, headers={"User-Agent": UA})
        with urllib.request.urlopen(request, timeout=60) as response:
            path.write_bytes(response.read())
    return path if binary else path.read_text(encoding="utf-8", errors="ignore")


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def html_rows(page):
    """Строки всех таблиц страницы: списки текстов ячеек."""
    rows = []
    for table in re.findall(r"<table.*?</table>", page, re.S):
        for row in re.findall(r"<tr.*?</tr>", table, re.S):
            rows.append([clean(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)])
    return rows


def norm(text):
    """Название для сравнения: строчные буквы, ё -> е, без кавычек и лишних пробелов."""
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"[«»\"“”]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def subject(name):
    """Код предмета или None, если это не ЕГЭ (собеседование, творческое испытание)."""
    name = norm(re.sub(r"\(профильная\)|\*", "", name, flags=re.I))
    return SUBJECTS.get(name)


def number(text):
    """Целое число из ячейки или None для «-», «*», «н/д» и т. п."""
    text = (text or "").replace("\xa0", "").replace(" ", "")
    return int(text) if re.fullmatch(r"\d+", text) else None


def add_stats(record, by_year, places_by_year, sources, skipped, title,
              paid_by_year=None, paid_places_by_year=None):
    """Записывает статистику по годам. Слишком большой балл значит другой набор экзаменов."""
    max_sum = 100 * len(record["exams"]) + 10
    paid_by_year, paid_places_by_year = paid_by_year or {}, paid_places_by_year or {}
    years = set(by_year) | set(places_by_year) | set(paid_by_year) | set(paid_places_by_year)
    for year in sorted(years):
        stat = {"year": year}
        for field, value in [("passing_score_budget", by_year.get(year)),
                             ("passing_score_paid", paid_by_year.get(year))]:
            if value is not None and value > max_sum:
                skipped.append(f"{title}, {year}: балл {value} больше {max_sum}, не берём")
            elif value is not None:
                stat[field] = value
        if places_by_year.get(year):
            stat["budget_places"] = places_by_year[year]
        if paid_places_by_year.get(year):
            stat["paid_places"] = paid_places_by_year[year]
        if len(stat) > 1:
            stat["source_url"] = sources.get(year, record["source_url"])
            record["stats"].append(stat)


# ---------- ВШЭ ----------

def hse(skipped):
    base = "https://ba.hse.ru/"
    code_re = re.compile(r"(?:направление подготовки|специальность)\s+(\d\d\.0[35]\.\d\d)", re.I)

    def table_by_program(page):
        """{(код направления, название, форма обучения): строка таблицы}."""
        result, code, form = {}, None, "full_time"
        for row in html_rows(page):
            first = row[0] if row else ""
            if first.startswith("Направление подготовки (специальность)"):
                result["header"] = row
                continue
            if re.search(r"очно-заочная форма", first, re.I):
                form = "part_time"
            elif re.search(r"очная форма", first, re.I):
                form = "full_time"
            match = code_re.search(first)
            if match:
                code = match.group(1)
            elif code and len(row) >= 2 and not first.startswith("Итого"):
                result[(code, norm(re.sub(r"\(.*?платная.*?\)", "", first)), form)] = row
        return result

    def column(header, start):
        """Номер столбца, заголовок которого начинается с start, или None."""
        return next((i for i, h in enumerate(header) if h.startswith(start)), None)

    # Проходные баллы по годам. С 2025 года рядом публикуется и балл на платные места
    scores, paid_scores = {}, {}
    for year in range(2021, 2026):
        url = f"{base}result{year}"
        rows = table_by_program(fetch(url))
        paid_column = column(rows.pop("header", []), "Проходной балл на платные")
        for key, row in rows.items():
            scores.setdefault(key[:2], {})[year] = number(row[1])
            if paid_column is not None and len(row) > paid_column:
                paid_scores.setdefault(key[:2], {})[year] = number(row[paid_column])

    # Бюджетные места: текущий год и прошлые
    places, paid_places, places_sources = {}, {}, {}
    for year, path in [(2026, "kolmest"), (2025, "kolmest25"), (2024, "kolmest24"), (2023, "kolmest2023")]:
        url = base + path
        try:
            rows = table_by_program(fetch(url))
        except Exception as error:
            skipped.append(f"места {year}: {url} не открылась ({error})")
            continue
        places_sources[year] = url
        # Столбец ищем по заголовку: в разные годы набор столбцов разный
        header = rows.pop("header")
        budget_column = column(header, "Бюджетные места")
        paid_column = column(header, "Места для поступающих по договорам")
        for key, row in rows.items():
            if len(row) > budget_column:
                places.setdefault(key, {})[year] = number(row[budget_column])
            if paid_column is not None and len(row) > paid_column:
                paid_places.setdefault(key, {})[year] = number(row[paid_column])

    # Программы и предметы берём из действующего перечня вступительных испытаний
    url = base + "minkrit"
    programs, current = [], None
    form, code = "full_time", None
    for row in html_rows(fetch(url)):
        first = row[0] if row else ""
        if re.search(r"очно-заочная форма", first, re.I):
            form = "part_time"
            continue
        if re.search(r"очная форма", first, re.I):
            form = "full_time"
            continue
        match = code_re.search(first)
        if match:
            code = match.group(1)
            continue
        if len(row) == 6 and re.fullmatch(r"\d+", first):
            current = {"code": code, "name": row[1], "online": row[2].lower() == "да",
                       "form": form, "exams": []}
            programs.append(current)
            exam_cells = row[3:]
        elif len(row) == 3 and current:
            exam_cells = row
        else:
            continue
        current["exams"].append((exam_cells[0], number(exam_cells[2]) or 0))

    records = []
    for p in programs:
        title = f"{p['name']} ({p['code']})"
        exams = []
        for names, min_score in p["exams"]:
            options = [subject(n) for n in names.split("/")]
            if None in options:
                skipped.append(f"{title}: внутреннее испытание «{names}», балл ЕГЭ несопоставим")
                break
            exam = [{"subject": s, "min_score": min_score} for s in options]
            exams.append(exam[0] if len(exam) == 1 else {"one_of": exam})
        else:
            key = (p["code"], norm(re.sub(r"\(.*?\)", "", p["name"])))
            if key not in scores:
                key = (p["code"], norm(p["name"]))
            by_year = scores.get(key)
            if by_year is None:
                # Программу могли переименовать. Если на направлении ровно одна программа
                # и в баллах, и в перечне, считаем их одной; иначе не угадываем
                same_code = [k for k in scores if k[0] == p["code"]]
                in_list = [q for q in programs if q["code"] == p["code"] and q["form"] == p["form"]]
                if len(same_code) == 1 and len(in_list) == 1:
                    key = same_code[0]
                    by_year = scores[key]
                    skipped.append(f"{title}: баллы взяты у «{same_code[0][1]}» (единственная программа направления)")
                else:
                    by_year = {}
            place_key = (p["code"], norm(p["name"]), p["form"])
            record = {
                "faculty": "",
                "name": p["name"] + (" (онлайн)" if p["online"] else ""),
                "direction_code": p["code"],
                "study_form": p["form"],
                "source_url": url,
                "exams": exams,
                "stats": [],
            }
            sources = {y: f"{base}result{y}" for y in by_year}
            for year, src in places_sources.items():
                sources.setdefault(year, src)
            add_stats(record, {y: s for y, s in by_year.items() if s}, places.get(place_key, {}),
                      sources, skipped, title,
                      paid_by_year={y: s for y, s in paid_scores.get(key, {}).items() if s},
                      paid_places_by_year=paid_places.get(place_key, {}))
            records.append(record)
    return {
        "name": "Национальный исследовательский университет «Высшая школа экономики»",
        "short_name": "ВШЭ", "website": "https://www.hse.ru", "has_dormitory": True,
        "source_url": base + "previous",
    }, records


# ---------- МГТУ им. Н. Э. Баумана ----------

def bmstu(skipped):
    api = "https://api.www.bmstu.ru/majors/baccalaureate-and-specialty?limit=100&offset=0"
    majors = json.loads(fetch(api))["data"]
    records = []
    for major in majors:
        url = f"https://bmstu.ru/bachelor/majors/{major['slug']}"
        title = f"{major['name']} ({major['code']})"
        page = fetch(url)
        data = json.loads(re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S).group(1))
        details = data["props"]["initialState"]["bachelorMajorsDetails"]["data"]
        info = details["additional"]

        exams, choice = [], []
        for item in details.get("points") or []:
            code = subject(item["title"])
            if code is None:
                skipped.append(f"{title}: внутреннее испытание «{item['title']}», балл ЕГЭ несопоставим")
                break
            exam = {"subject": code, "min_score": item.get("point") or 0}
            (choice if item.get("isChoice") else exams).append(exam)
        else:
            if len(choice) == 1:
                exams.append(choice[0])
            elif choice:
                exams.append({"one_of": choice})
            if not exams:
                skipped.append(f"{title}: на странице нет вступительных испытаний")
                continue

            places = next((p["count"] for p in details.get("places") or [] if p["title"].startswith("Бюджет")), None)
            price = next((p["value"] for p in details.get("price") or [] if p.get("studyForm") == "Очная"), None)
            record = {
                "faculty": ", ".join(clean(f["title"]) for f in major.get("faculties", [])),
                "name": major["name"],
                "direction_code": major["code"],
                "study_form": "full_time",
                "source_url": url,
                "exams": exams,
                "stats": [],
            }
            if price and number(price):
                record["tuition_per_year"] = number(price)
            by_year = {int(y): number(str(v.get("budget"))) for y, v in (info.get("oldPoints") or {}).items()}
            last_year = max(by_year) if by_year else 2026
            add_stats(record, {y: s for y, s in by_year.items() if s}, {last_year: places} if places else {},
                      {}, skipped, title)
            records.append(record)
    return {
        "name": "Московский государственный технический университет им. Н.Э. Баумана",
        "short_name": "МГТУ им. Баумана", "website": "https://bmstu.ru", "has_dormitory": True,
        "source_url": "https://bmstu.ru/bachelor/previous-points",
    }, records


# ---------- Сеченовский Университет ----------

def sechenov(skipped):
    """Всё берём из каталога: короткая карточка (предметы, профиль, стоимость)
    связана через data-modal-id со всплывающей (места, проходной балл, ссылка на программу)."""
    base = "https://priem.sechenov.ru"
    catalog_url = base + "/undergraduate/prokhodnye-bally-za-2025-god/"
    page = fetch(catalog_url)

    def blocks(marker):
        starts = [m.start() for m in re.finditer(marker, page)]
        return [page[a:b] for a, b in zip(starts, starts[1:] + [len(page)])]

    modals = {}
    for block in blocks(r'<div class="course-modal" id="'):
        modals[re.search(r'id="([^"]+)"', block).group(1)] = block

    records = []
    for card in blocks(r'<div class="course-card" data-modal-id="'):
        card = card[:card.find("course-card__footer") + 2000]
        modal = modals.get(re.search(r'data-modal-id="([^"]+)"', card).group(1), "")
        link = re.search(r'href="(/undergraduate/[^"]+/)" class="btn upp"', modal)
        if not link or "filial" in link.group(1):
            continue  # филиалы в других городах не берём
        url = base + link.group(1)
        heading = clean(re.search(r'course-card__title[^>]*>(.*?)</span>', card, re.S).group(1))
        code = re.search(r"\d\d\.0[35]\.\d\d", heading).group(0)
        profile = re.search(r"Профиль\s*-\s*([^<]+)<", card)
        name = clean(profile.group(1)) if profile else heading.replace(code, "").strip()
        institute = clean(re.search(r'course-card__institution[^>]*>(.*?)</span>', card, re.S).group(1))
        title = f"{name} ({code})"

        # Предметы ЕГЭ: первый список после «Общеобразовательные вступительные испытания»
        start = card.find("Общеобразовательные вступительные испытания")
        block = card[start:card.find("</ul>", start)]
        exams = []
        for label, value in re.findall(r'cell__label">(.*?)</span>\s*<span class="[^"]*cell__value">(.*?)</span>',
                                       block, re.S):
            label = re.sub(r"<b>.*?</b>", "", label, flags=re.S)
            names = [clean(n) for n in clean(label).split("/")]
            scores = [number(v) or 0 for v in clean(value).split("/")]
            pairs = [(subject(n), m) for n, m in zip(names, scores) if norm(n) not in OTHER_LANGUAGES]
            if not pairs or any(c is None for c, _ in pairs):
                skipped.append(f"{title}: непонятный предмет {names}")
                exams = None
                break
            exam = list({c: {"subject": c, "min_score": m} for c, m in pairs}.values())  # без повторов
            exams.append(exam[0] if len(exam) == 1 else {"one_of": exam})
        if not exams:
            if exams == []:
                skipped.append(f"{title}: в карточке нет вступительных испытаний")
            continue

        # Бюджетные места: квоты плюс общий конкурс (на текущий год)
        values = {clean(l): number(clean(v)) for l, v in re.findall(
            r'cell__label">(Места в рамках[^<]*)</span>\s*<span class="[^"]*cell__value">(.*?)</span>',
            modal, re.S)}
        budget = sum(v or 0 for l, v in values.items() if "квоты" in l or "контрольных цифр" in l) or None

        passing_block = modal[modal.find("Минимальная сумма конкурсных баллов"):]
        passing = re.search(r"контрольных цифр приёма.*?(\d+)", clean(passing_block.split("договорам")[0]))
        year = re.search(r"Минимальная сумма конкурсных баллов за (\d{4})", modal)
        form = "part_time" if re.search(r"course-card__form-education\">\s*Очно-заочная", card) else "full_time"
        price = re.search(r"course-card__price-value\">\s*([\d\s]+)₽", card)
        record = {
            "faculty": institute,
            "name": name,
            "direction_code": code,
            "study_form": form,
            "source_url": url,
            "exams": exams,
            "stats": [],
        }
        if price:
            record["tuition_per_year"] = number(price.group(1))
        by_year = {int(year.group(1)): int(passing.group(1))} if passing and year else {}
        add_stats(record, by_year, {2026: budget} if budget else {},
                  {y: catalog_url for y in by_year} | {2026: catalog_url}, skipped, title)
        records.append(record)
    return {
        "name": "Первый МГМУ им. И.М. Сеченова (Сеченовский Университет)",
        "short_name": "Сеченовский", "website": "https://www.sechenov.ru", "has_dormitory": True,
        "source_url": catalog_url,
    }, records


# ---------- РАНХиГС ----------

def ranepa(skipped):
    import pdfplumber  # нужен только здесь

    passing_url = "https://www.ranepa.ru/bakalavriat/prokhodnoy-ball/"
    exams_url = "https://www.ranepa.ru/upload/doc/pk/2026/Perechen_VI-2026.pdf"
    places_url = "https://www.ranepa.ru/upload/doc/pk/2026/Академия_БАК_цифры бюд.pdf"
    forms = {"очная": "full_time", "очно-заочная": "part_time", "заочная": "distance"}

    def initials(institute):
        """«Институт экономики, математики и ...» -> «ИЭМИТ», как в таблице проходных баллов."""
        words = re.findall(r"[А-ЯЁа-яё]+", institute)
        return "".join(w[0].upper() for w in words if len(w) > 2)

    def program_names(cell):
        """В одной ячейке может быть несколько программ: «1. Образовательная программа "А" 2. ...»."""
        names = re.findall(r"программа\s*[\"«“]([^\"»”]+)[\"»”]", cell.replace("\n", " "))
        return [clean(n) for n in names] or [clean(cell)]

    def program_name(cell):
        return program_names(cell)[0]

    def find_key(table, key, title, what, skipped):
        """Ключ (название, подразделение, форма) в таблице. Если точного нет, ищем программу
        той же формы, чьё название содержит наше (или наоборот), и берём её, только если она одна."""
        if key in table:
            return key
        name, _, form = key
        similar = [k for k in table if k[2] == form and (name in k[0] or k[0] in name)]
        if len(similar) == 1:
            skipped.append(f"{title}: {what} взяты у «{similar[0][0]}» ({similar[0][1]}), название отличается")
            return similar[0]
        skipped.append(f"{title} ({key[1]}): {what} не нашлись")
        return None

    # Проходные баллы: «Название (ИНСТИТУТ), форма, бюджет» | 2023 | 2024 | 2025.
    # Вместо сокращения в скобках может стоять полное название подразделения
    page = fetch(passing_url)
    first_table = re.findall(r"<table.*?</table>", page, re.S)[0]
    header, *rows = html_rows(first_table)
    years = [int(y) for y in header[2:]]
    scores = {}
    for row in rows:
        match = re.match(r"(.+)\s*\(([^()]+)\)\s*,?\s*(очно-заочная|очная|заочная)", row[1])
        if not match:
            skipped.append(f"проходные баллы: не разобрал строку «{row[1]}»")
            continue
        name, institute, form = match.groups()
        if not re.fullmatch(r"[А-ЯЁA-Z]+", institute):
            institute = initials(institute)
        scores[(norm(name), institute, forms[form])] = {y: number(v) for y, v in zip(years, row[2:])}

    # Места на бюджет (текущий год)
    places = {}
    with pdfplumber.open(fetch(places_url, binary=True)) as pdf:
        for page_ in pdf.pages:
            for table in page_.extract_tables():
                for row in table:
                    if row and row[0] and re.match(r"\d\d\.0[35]\.\d\d", row[0]):
                        institute = initials(row[2] or "")
                        for form, cell in zip(["full_time", "part_time", "distance"], row[3:6]):
                            if number(cell):
                                places[(norm(program_name(row[1])), institute, form)] = number(cell)

    # Вступительные испытания для бюджетных мест. Строка с источником финансирования
    # открывает блок: «БЮДЖЕТ» — наш, «платные места» — пропускаем до следующего бюджетного.
    # Код, название и подразделение есть только в первой строке программы
    programs, current, last_info = [], [], None
    with pdfplumber.open(fetch(exams_url, binary=True)) as pdf:
        for page_ in pdf.pages:
            for table in page_.extract_tables():
                for row in table:
                    row = [(c or "").replace("\n", " ").strip() for c in row]
                    if len(row) < 7:
                        continue
                    if re.match(r"\d\d\.0[35]\.\d\d", row[0]):
                        last_info = row[:4]
                    if row[4]:
                        current = []
                        if "БЮДЖЕТ" in row[4].upper() and last_info:
                            code, names, institute, form = last_info
                            for name in program_names(names):
                                current.append({"code": code[:8], "name": name, "institute": initials(institute),
                                                "form": forms.get(form.lower()), "exams": []})
                            programs.extend(current)
                    exam = row[6]
                    if not current or not exam or re.search(r"по выбору|для поступающих|Наименование", exam):
                        continue
                    for program in current:
                        program["exams"].append((row[5], exam))

    records = []
    for p in programs:
        title = f"{p['name']} ({p['code']})"
        if p["form"] is None:
            skipped.append(f"{title}: непонятная форма обучения")
            continue
        groups = {}
        for priority, name in p["exams"]:
            groups.setdefault(priority, []).append(name)
        exams, ok = [], True
        for priority, names in groups.items():
            codes = [subject(n) for n in names]
            if None in codes:
                skipped.append(f"{title}: внутреннее испытание {names}, балл ЕГЭ несопоставим")
                ok = False
                break
            # Минимальные баллы РАНХиГС одинаковы для всех программ: файл min_ball_2026.pdf
            exam = [{"subject": c, "min_score": RANEPA_MIN[c]} for c in dict.fromkeys(codes)]
            exams.append(exam[0] if len(exam) == 1 else {"one_of": exam})
        if not ok or not exams:
            continue
        key = (norm(p["name"]), p["institute"], p["form"])
        record = {
            "faculty": p["institute"],
            "name": p["name"],
            "direction_code": p["code"],
            "study_form": p["form"],
            "source_url": exams_url,
            "exams": exams,
            "stats": [],
        }
        score_key = find_key(scores, key, title, "баллы", skipped)
        place_key = find_key(places, key, title, "места", skipped)
        by_year = {y: s for y, s in (scores.get(score_key) or {}).items() if s}
        sources = {y: passing_url for y in by_year}
        sources[2026] = places_url
        add_stats(record, by_year, {2026: places[place_key]} if place_key else {}, sources, skipped, title)
        records.append(record)
    return {
        "name": "Российская академия народного хозяйства и государственной службы при Президенте РФ",
        "short_name": "РАНХиГС", "website": "https://www.ranepa.ru", "has_dormitory": True,
        "source_url": passing_url,
    }, records


# Минимальные баллы РАНХиГС для бюджета, очная форма (min_ball_2026.pdf)
RANEPA_MIN = {
    "russian": 70, "math": 60, "social": 70, "english": 70, "informatics": 60, "history": 70,
    "physics": 60, "chemistry": 0, "geography": 60, "literature": 70, "biology": 60,
}

COLLECTORS = {"hse": hse, "bmstu": bmstu, "sechenov": sechenov, "ranepa": ranepa}


def collect(code):
    skipped = []
    info, programs = COLLECTORS[code](skipped)

    # Одинаковые (факультет, название, форма) различаем кодом направления
    keys = {}
    for p in programs:
        keys.setdefault((p["faculty"], p["name"], p["study_form"]), []).append(p)
    for group in keys.values():
        if len(group) > 1:
            for p in group:
                p["name"] = f"{p['name']} ({p['direction_code']})"

    data = {"code": code, **info, "verified": False, "programs": programs}
    (OUT_DIR / f"{code}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (CACHE / f"skipped_{code}.txt").write_text("\n".join(skipped) + "\n", encoding="utf-8")
    with_scores = sum(1 for p in programs if any("passing_score_budget" in s for s in p["stats"]))
    print(f"{code}: программ {len(programs)}, с проходными баллами {with_scores}, пропусков {len(skipped)}")


def main():
    global FRESH
    parser = argparse.ArgumentParser(description="Сбор программ с официальных сайтов вузов")
    parser.add_argument("codes", nargs="*", help=f"коды вузов: {', '.join(COLLECTORS)}")
    parser.add_argument("--fresh", action="store_true", help="скачать страницы заново")
    args = parser.parse_args()

    unknown = [code for code in args.codes if code not in COLLECTORS]
    if unknown:
        sys.exit(f"Неизвестные вузы: {', '.join(unknown)}. Есть: {', '.join(COLLECTORS)}")
    FRESH = args.fresh
    CACHE.mkdir(parents=True, exist_ok=True)
    for code in args.codes or COLLECTORS:
        collect(code)


if __name__ == "__main__":
    main()
