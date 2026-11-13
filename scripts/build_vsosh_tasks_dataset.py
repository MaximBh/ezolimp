#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen, urlretrieve


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_CACHE_DIR = ROOT_DIR / "backend" / "cache"
PDF_CACHE_DIR = BACKEND_CACHE_DIR / "pdf_sources"
TASKS_JSON_PATH = ROOT_DIR / "tasks.json"

sys.path.insert(0, str(ROOT_DIR))
from backend.app.pdf_parser import _load_entries, _similarity  # noqa: E402


ARCHIVE_YEAR_IDS = [
    "2025_2026",
    "2024_2025",
    "2023_2024",
    "2022_2023",
    "2021_2022",
    "2020_2021",
    "2019_2020",
    "2018_2019",
]

SUBJECT_CONFIGS = [
    {"name": "математика", "slugs": {"math"}},
    {"name": "информатика", "slugs": {"iikt"}},
    {"name": "физика", "slugs": {"phys"}},
    {"name": "химия", "slugs": {"chem"}},
    {"name": "биология", "slugs": {"biol"}},
    {"name": "английский", "slugs": {"engl"}},
    {"name": "русский", "slugs": {"russ"}},
    {"name": "история", "slugs": {"hist"}},
    {"name": "география", "slugs": {"geog"}},
    {"name": "обществознание", "slugs": {"soci"}},
    {"name": "право", "slugs": {"law"}},
    {"name": "литература", "slugs": {"litr"}},
    {"name": "экология", "slugs": {"ekol"}},
    {
        "name": "робототехника",
        "slugs": {"robo", "tech"},
        "required_name_tokens": {"robo", "techrobo"},
    },
]

TARGET_GRADES = list(range(5, 12))
TARGET_PER_SUBJECT_GRADE = 20
TARGET_TOTAL_TASKS = 2000
BASE_URL = "https://xn--b1ayi3a.xn--l1afu.xn--p1ai/archive/table/tasks/years/"
CURRENT_TASKS_API_URL = "https://vos.olimpiada.ru/api/getTasks"
CURRENT_FILES_BASE_URL = "https://vos.olimpiada.ru"
CURRENT_SEASON = "2026-27"

STAGE_RANK = {
    "school": 0,
    "prigl": 1,
    "mun": 2,
    "reg": 3,
    "zakl": 4,
    "final": 4,
}

PDF_LINK_RE = re.compile(r"""href=['"]([^'"]+\.pdf)['"]""", re.IGNORECASE)
PDF_META_RE = re.compile(
    r"/(?P<season>\d{4}-\d{2})/"
    r"(?P<stage>school|prigl|mun|reg|zakl|final)/"
    r"(?P<slug>[a-z0-9]+)/"
    r"(?P<name>[^/?#]+\.pdf)$",
    re.IGNORECASE,
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[\.\?!])\s+")
WHITESPACE_RE = re.compile(r"\s+")
TASK_WORD_RE = re.compile(r"(?:задач[аеи]|задани[ея]|task)\s+\d{1,3}", re.IGNORECASE)
TASK_DOCUMENT_HEADING_RE = re.compile(
    r"^\s*(?:задания?|задачи|разбор\s+заданий|ответы|решения)\s+"
    r"(?:(?:школьного|пригласительного|муниципального|регионального|заключительного)\s+этапа|"
    r"всероссийской\s+олимпиады)\b",
    re.IGNORECASE,
)
ANSWER_PATTERNS = [
    re.compile(r"(?i)\bитоговый\s+ответ(?:ы)?\s*[:.\-–—]\s*(.+)$"),
    re.compile(r"(?i)\bответ(?:ы)?\s*[:.\-–—]\s*(.+)$"),
    re.compile(r"(?i)\bfinal\s+answer\s*[:\-]\s*(.+)$"),
    re.compile(r"(?i)\banswers?\s*[:.\-–—]\s*(.+)$"),
    re.compile(r"(?i)\b(?:respuestas?|r[eé]ponses?|rispost[ae]|antwort(?:en)?)\s*[:.\-–—]\s*(.+)$"),
    re.compile(r"答案\s*[:：]\s*(.+)$"),
]
_REPEATED_ANSWER_LABEL_RE = re.compile(
    r"(?:^|\s)(?:(?:итоговый)\s+)?(?:ответ|ответы|answers?)\s*[:.]",
    re.IGNORECASE,
)
_VARIANT_REFERENCE_RE = re.compile(
    r"варианты?\s+задан(?:ия|ий|ие)\s+(?:смотрите|см\.?)\s+(?:на\s+)?стр\.?\s*\d+\.?",
    re.IGNORECASE,
)
_INLINE_TASK_DOCUMENT_HEADER_RE = re.compile(
    r"\bзадания?\s+(?:пригласительного|школьного|муниципального|регионального|заключительного)\s+"
    r"этапа\s+всош\s+20\d{2}(?:[/-]\d{2,4})?\s+по\s+.{1,100}?\b(?:[5-9]|1[01])\s+класс\b",
    re.IGNORECASE,
)
_BARE_ENGLISH_ANSWER_RE = re.compile(
    r"\bAnswers?\s+((?:[A-H]|\d{1,2})(?:(?:\s+|[,;]\s*)(?:[A-H]|\d{1,2}))*)"
)
_ANSWER_TRIM_RE = re.compile(
    r"\s+(?:за\s+каждый\s+правильный\s+ответ|за\s+каждый\s+верный\s+ответ|"
    r"за\s+каждый\s+верный\s+выбор|"
    r"за\s+каждое\s+верное\s+(?:соответствие|соотнесение|сопоставление)|"
    r"за\s+верный\s+ответ|за\s+правильный\s+ответ|"
    r"за\s+каждое?\s+совпадение(?:\s+с\s+правильным\s+ответом)?|"
    r"балл\s+за\s+(?:каждый|каждое|каждую)|"
    r"по\s+\d{1,2}\s+балл\w*\s+за\s+кажд\w*|\d{1,2}\s+балл\w*|"
    r"максимум\s+за\s+задание|"
    r"максимальн\w*\s+балл|решение|разбор|solution|explanation|пояснение|"
    r"критери(?:й|и)(?:\s+оценивания)?|точное\s+совпадение|"
    r"полное\s+совпадение|"
    r"for\s+each\s+(?:correct\s+)?answer|(?:one|two|three|\d+)\s+points?\s+for|"
    r"(?:un\s+)?puntos?\s+por\s+cada|(?:un\s+)?points?\s+par\s+bonne\s+r[eé]ponse|"
    r"(?:un\s+)?point\s+pour\s+chaque\s+(?:bonne\s+)?r[eé]ponse|"
    r"(?:ein\s+)?punkt(?:e)?\s+f[uü]r\s+jede\w*\s+(?:richtige\s+)?antwort|"
    r"(?:un\s+)?punto\s+per\s+ogni\s+(?:risposta\s+)?corrett\w*|"
    r"верный\s+ответ|правильный\s+ответ|неверный\s+ответ)(?:[.:,\s]|$)",
    re.IGNORECASE,
)
_ANSWER_POSTFIX_TRIM_RE = re.compile(
    r"\s+(?:к\s+задаче\s+\d|A\s+B\s+C\s+D\s+E\b|"
    r"задани(?:я|е)\s+\d{1,3}(?:\s*[–—-]\s*\d{1,3})?\b)",
    re.IGNORECASE,
)
_ANSWER_SCORING_MARKER_RE = re.compile(
    r"\s+(?:точное\s+совпадение(?:\s+с\s+правильным\s+ответом)?|"
    r"полное\s+совпадение(?:\s+с\s+правильным\s+ответом)?|"
    r"за\s+кажд(?:ый|ое|ую)\s+(?:верн\w*|правильн\w*|совпадение)|"
    r"за\s+каждое?\s+совпадение(?:\s+с\s+правильным\s+ответом)?|"
    r"балл\s+за\s+(?:каждый|каждое|каждую)|"
    r"по\s+\d{1,2}\s+балл\w*\s+за\s+кажд\w*|\d{1,2}\s+балл\w*|"
    r"критери(?:й|и)(?:\s+оценивания)?|"
    r"максимум\s+за\s+задание|максимальн\w*\s+балл|всего\s+за\s+задание)[.:,\s]",
    re.IGNORECASE,
)

CURRENT_SUBJECT_NAMES = {
    "ai": "информатика: искусственный интеллект",
    "astr": "астрономия",
    "biol": "биология",
    "chem": "химия",
    "econ": "экономика",
    "ekol": "экология",
    "engl": "английский",
    "geog": "география",
    "hist": "история",
    "law": "право",
    "litr": "литература",
    "math": "математика",
    "phys": "физика",
    "prog": "информатика: программирование",
    "robo": "робототехника",
    "russ": "русский",
    "secr": "информатика: информационная безопасность",
    "soci": "обществознание",
}

STOP_TOKENS = {
    "tasks",
    "task",
    "taskskrit",
    "sol",
    "ans",
    "answer",
    "sch",
    "prigl",
    "mun",
    "reg",
    "zakl",
    "teor",
    "prak",
    "msk",
    "tur1",
    "tur2",
    "secr",
    "home",
}

PDF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
FAILED_URLS: set[str] = set()


@dataclass
class PdfFile:
    url: str
    year_id: str
    season: str
    stage: str
    slug: str
    name: str
    kind: str
    grades: list[int]
    subject_name: str = ""


def _fetch_archive_pdf_links(year_id: str) -> list[str]:
    url = f"{BASE_URL}{year_id}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urlopen(request, timeout=30).read().decode("utf-8", errors="ignore")
    links = [urljoin(url, m.group(1)) for m in PDF_LINK_RE.finditer(html)]
    deduped: list[str] = []
    seen = set()
    for link in links:
        if link in seen:
            continue
        seen.add(link)
        deduped.append(link)
    return deduped


def _fetch_current_pdf_catalog() -> list[PdfFile]:
    request = Request(
        CURRENT_TASKS_API_URL,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with urlopen(request, timeout=40) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))

    catalog: list[PdfFile] = []
    seen: set[str] = set()
    for row in payload.get("data", []):
        if not isinstance(row, dict) or str(row.get("yname") or "").strip() != "2026/2027":
            continue
        slug_hint = str(row.get("subject_psevdo") or "").strip().lower()
        official_subject_name = _clean_text(str(row.get("subject") or ""), limit=120)
        if not slug_hint or not official_subject_name:
            continue
        html = str(row.get("tasks") or "")
        for match in PDF_LINK_RE.finditer(html):
            link = urljoin(CURRENT_FILES_BASE_URL, match.group(1))
            if link in seen:
                continue
            parsed = PDF_META_RE.search(link)
            if not parsed or parsed.group("season").lower() != CURRENT_SEASON:
                continue
            slug = parsed.group("slug").lower()
            if slug != slug_hint:
                continue
            name = parsed.group("name").lower()
            grades = _extract_grades_from_name(name)
            if not grades or not (set(grades) & set(TARGET_GRADES)):
                continue
            stage = parsed.group("stage").lower()
            if stage == "final":
                stage = "zakl"
            kind = _classify_kind(name)
            if kind not in {"tasks", "solution"}:
                continue
            seen.add(link)
            catalog.append(
                PdfFile(
                    url=link,
                    year_id="2026_2027",
                    season=CURRENT_SEASON,
                    stage=stage,
                    slug=slug,
                    name=name,
                    kind=kind,
                    grades=grades,
                    subject_name=official_subject_name,
                )
            )
    return catalog


def _extract_grades_from_name(name: str) -> list[int]:
    nums = [int(x) for x in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", name)]
    grades = sorted({n for n in nums if 1 <= n <= 11})
    if not grades:
        return []
    if len(grades) >= 2 and grades[-1] - grades[0] <= 6:
        return list(range(grades[0], grades[-1] + 1))
    return grades


def _classify_kind(name: str) -> str:
    lower = name.lower()
    if "taskskrit" in lower or "criteria" in lower:
        return "other"
    if "task" in lower and not any(token in lower for token in ("sol", "ans", "answer")):
        return "tasks"
    if any(token in lower for token in ("sol", "ans", "answer")):
        return "solution"
    return "other"


def _build_catalog() -> list[PdfFile]:
    catalog: list[PdfFile] = []
    for year_id in ARCHIVE_YEAR_IDS:
        links = _fetch_archive_pdf_links(year_id)
        for link in links:
            parsed = PDF_META_RE.search(link)
            if not parsed:
                continue
            season = parsed.group("season").lower()
            stage = parsed.group("stage").lower()
            slug = parsed.group("slug").lower()
            name = parsed.group("name").lower()
            kind = _classify_kind(name)
            grades = _extract_grades_from_name(name)
            if not grades:
                continue
            catalog.append(
                PdfFile(
                    url=link,
                    year_id=year_id,
                    season=season,
                    stage=stage,
                    slug=slug,
                    name=name,
                    kind=kind,
                    grades=grades,
                )
            )
    return catalog


def _pdf_cache_path(url: str) -> Path:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix != ".pdf":
        suffix = ".pdf"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return PDF_CACHE_DIR / f"{digest}{suffix}"


def _ensure_local_pdf(url: str) -> Path:
    path = _pdf_cache_path(url)
    if path.exists() and path.stat().st_size > 0:
        return path
    tmp = path.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    urlretrieve(url, tmp)
    if not tmp.exists() or tmp.stat().st_size <= 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download PDF: {url}")
    tmp.replace(path)
    return path


def _clean_text(text: str, limit: int = 12000) -> str:
    clean = unicodedata.normalize("NFC", str(text or "").replace("\ufeff", " "))
    clean = re.sub(r"[\uFFFE\uFFFF]", "", clean)
    clean = clean.replace("\uFFFD", "□")
    clean = WHITESPACE_RE.sub(" ", clean).strip()
    clean = _INLINE_TASK_DOCUMENT_HEADER_RE.sub(" ", clean)
    clean = WHITESPACE_RE.sub(" ", clean).strip()
    return clean[:limit].strip()


def _looks_like_task_text(text: str) -> bool:
    if not text or len(text) < 35:
        return False
    if len(text) > 20000:
        return False
    if TASK_DOCUMENT_HEADING_RE.match(text):
        return False
    # Variant-only pages often begin with a task label and a cross-reference to
    # the table on another page. That is not a task condition on its own.
    without_variant_reference = _VARIANT_REFERENCE_RE.sub(" ", text)
    if len(WHITESPACE_RE.sub(" ", without_variant_reference).strip(" .:-")) < 35:
        return False
    if TASK_WORD_RE.findall(text) and len(TASK_WORD_RE.findall(text)) > 4:
        return False
    return True


def _tokenize_name(name: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", name.lower()))
    return {token for token in tokens if token not in STOP_TOKENS and len(token) > 1}


def _solution_url_candidates(task_url: str) -> list[str]:
    repl = [
        ("tasks-", "sol-"),
        ("tasks_", "sol_"),
        ("taskskrit-", "ans-"),
        ("taskskrit_", "ans_"),
        ("tasks-", "ans-"),
        ("tasks_", "ans_"),
        ("task-", "sol-"),
        ("task_", "sol_"),
    ]
    candidates = [task_url]
    for old, new in repl:
        if old in task_url:
            candidates.append(task_url.replace(old, new))
    deduped: list[str] = []
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return deduped


def _match_solution_file(
    task_file: PdfFile,
    solution_lookup: dict[tuple[str, str, str], list[PdfFile]],
    all_solution_urls: set[str],
) -> PdfFile | None:
    for candidate_url in _solution_url_candidates(task_file.url):
        if candidate_url in all_solution_urls:
            for f in solution_lookup.get((task_file.season, task_file.stage, task_file.slug), []):
                if f.url == candidate_url:
                    return f

    candidates = solution_lookup.get((task_file.season, task_file.stage, task_file.slug), [])
    if not candidates:
        return None

    task_tokens = _tokenize_name(task_file.name)
    task_grades = set(task_file.grades)
    best_score = float("-inf")
    best: PdfFile | None = None
    for candidate in candidates:
        overlap = len(task_grades & set(candidate.grades))
        token_overlap = len(task_tokens & _tokenize_name(candidate.name))
        score = overlap * 50 + token_overlap * 5 - abs(len(candidate.name) - len(task_file.name)) * 0.01
        if score > best_score:
            best_score = score
            best = candidate
    return best


def _extract_answer(text: str) -> str:
    clean = _clean_text(text, limit=4000)
    if not clean:
        return "see solution"
    if re.match(r"^(?:критери(?:й|и)|criteria|scoring)\b", clean, re.IGNORECASE):
        return "see solution"
    scoring_marker = _ANSWER_SCORING_MARKER_RE.search(clean)
    scoring_start = scoring_marker.start() if scoring_marker else None
    for pattern in ANSWER_PATTERNS:
        for match in pattern.finditer(clean):
            if scoring_start is not None and match.start() > scoring_start:
                continue
            prefix = clean[max(0, match.start() - 40):match.start()]
            if re.search(
                r"(?:верн\w*|правильн\w*|неверн\w*|отсутствующ\w*|"
                r"correct|right|wrong|incorrect|richtige|correcta|correcte)\s+$",
                prefix,
                re.IGNORECASE,
            ):
                continue
            raw = match.group(1)
            # Some answer PDFs flatten several variant keys into one text block.
            # Without a variant boundary we cannot safely choose one of them.
            if _REPEATED_ANSWER_LABEL_RE.search(raw):
                return "see solution"
            trimmed = _ANSWER_TRIM_RE.split(raw, maxsplit=1)[0]
            trimmed = _ANSWER_POSTFIX_TRIM_RE.split(trimmed, maxsplit=1)[0]
            answer = _clean_text(trimmed, limit=256).rstrip(".")
            answer = re.sub(r"\s*\(\s*по\s+\d{1,2}\s+балл\w*\s*\)", "", answer, flags=re.IGNORECASE)
            answer = _ANSWER_SCORING_MARKER_RE.split(answer, maxsplit=1)[0].rstrip(" .,:;–—-")
            if re.match(r"^(?:критери(?:й|и)|criteria|scoring)\b", answer, re.IGNORECASE):
                continue
            if re.match(r"^\d+\s+балл(?:а|ов)?\b", answer, re.IGNORECASE):
                continue
            if answer:
                return answer

    bare_answer = _BARE_ENGLISH_ANSWER_RE.search(clean)
    if bare_answer and (scoring_start is None or bare_answer.start() < scoring_start):
        return _clean_text(bare_answer.group(1), limit=1800).strip(" .,:;–—-")

    if scoring_marker:
        key_candidate = _clean_text(clean[:scoring_start], limit=1800).strip(" .,:;–—-")
        if (
            key_candidate
            and len(key_candidate) <= 180
            and "?" not in key_candidate
            and not re.match(r"^\d+$", key_candidate)
            and not re.search(
                r"\b(?:задач[аеи]|задани[ея]|выберите|найдите|укажите|отметьте|"
                r"сопоставьте|решите|заполните|определите|ответьте|рассмотрим|критери[йи]|решение)\b",
                key_candidate,
                re.IGNORECASE,
            )
        ):
            return key_candidate
    return "see solution"


def _build_ai_explanation(statement: str, official_solution: str, answer: str, subject: str, grade: int) -> str:
    statement_clean = _clean_text(statement, limit=1800)
    official_clean = _clean_text(official_solution, limit=2200)

    idea = ""
    if statement_clean:
        first_sentence = SENTENCE_SPLIT_RE.split(statement_clean)[0].strip()
        idea = first_sentence[:260]
    if not idea:
        idea = f"Рассматриваем задачу по предмету «{subject}» для {grade} класса."

    lines = []
    for chunk in re.split(r"[\n\r]+", official_solution or ""):
        chunk_clean = _clean_text(chunk, limit=350)
        if len(chunk_clean) < 18:
            continue
        if chunk_clean.lower().startswith(("ответ", "итоговый ответ", "final answer")):
            continue
        lines.append(chunk_clean)
        if len(lines) >= 4:
            break

    if not lines and official_clean:
        sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(official_clean) if len(s.strip()) > 18]
        lines = sentences[:4]

    if not lines:
        fallback = []
        if statement_clean:
            fallback.append(f"Из условия выделяем ключевые данные: {statement_clean[:280]}.")
        fallback.append("Строим последовательное решение с проверкой ограничений задачи.")
        if answer and answer != "see solution":
            fallback.append(f"Проверяем вычисления и фиксируем ответ: {answer}.")
        lines = fallback

    steps = [f"{idx}. {line}" for idx, line in enumerate(lines, start=1)]
    answer_line = answer if answer else "см. официальное решение"
    payload = [
        "Решение (сгенерировано нейросетью):",
        f"Идея: {idea}",
        *steps,
        f"Итоговый ответ: {answer_line}",
    ]
    return "\n".join(payload).strip()


def _difficulty_and_points(index_in_bucket: int) -> tuple[str, int]:
    if index_in_bucket < 7:
        return "easy", 6
    if index_in_bucket < 14:
        return "medium", 10
    return "hard", 14


def _season_start_year(season: str, fallback_year_id: str) -> str:
    match = re.match(r"(\d{4})-\d{2}", season or "")
    if match:
        return match.group(1)
    return fallback_year_id.split("_", 1)[0]


def _subject_allows_file(subject_cfg: dict[str, Any], pdf_file: PdfFile) -> bool:
    if pdf_file.slug not in subject_cfg["slugs"]:
        return False
    required_tokens = set(subject_cfg.get("required_name_tokens") or set())
    if not required_tokens:
        return True
    name = pdf_file.name.lower()
    return any(token in name for token in required_tokens)


def _grade_distance(target_grade: int, source_grades: Iterable[int]) -> int:
    grades = list(source_grades)
    if not grades:
        return 99
    return min(abs(target_grade - g) for g in grades)


def _candidate_score(target_grade: int, task_file: PdfFile, entries_count: int) -> float:
    dist = _grade_distance(target_grade, task_file.grades)
    stage_rank = STAGE_RANK.get(task_file.stage, 10)
    season_start = int(_season_start_year(task_file.season, task_file.year_id))
    score = 600.0
    score -= dist * 80
    if target_grade in task_file.grades:
        score += 120
    score -= stage_rank * 6
    if task_file.stage == "school":
        score += 28
    elif task_file.stage == "prigl":
        score += 18
    score += max(0, season_start - 2017) * 2
    score += min(entries_count, 30)
    return score


def _normalize_source_fragments(entry: dict[str, Any], page_start: int | None, page_end: int | None) -> list[dict[str, Any]]:
    raw = entry.get("source_fragments") or []
    normalized: list[dict[str, Any]] = []
    for idx, fragment in enumerate(raw, start=1):
        try:
            page = int(fragment.get("page"))
        except Exception:
            continue
        normalized.append(
            {
                "page": page,
                "x": 0.0 if fragment.get("x") is None else float(fragment.get("x")),
                "y": 0.0 if fragment.get("y") is None else float(fragment.get("y")),
                "width": 1.0 if fragment.get("width") is None else float(fragment.get("width")),
                "height": 1.0 if fragment.get("height") is None else float(fragment.get("height")),
                "unit": str(fragment.get("unit") or "ratio"),
                "order_index": int(fragment.get("order_index") or idx),
            }
        )
    if normalized:
        return normalized

    if page_start and page_end and page_end >= page_start:
        fallback = []
        order = 1
        for page in range(page_start, page_end + 1):
            fallback.append(
                {
                    "page": page,
                    "x": 0.0,
                    "y": 0.0,
                    "width": 1.0,
                    "height": 1.0,
                    "unit": "ratio",
                    "order_index": order,
                }
            )
            order += 1
        return fallback
    return []


def _load_entries_cached(url: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if url in FAILED_URLS:
        return []
    cached = cache.get(url)
    if cached is not None:
        return cached
    try:
        pdf_path = _ensure_local_pdf(url)
        entries = _load_entries(pdf_path)
    except Exception:
        FAILED_URLS.add(url)
        cache[url] = []
        return []
    cache[url] = entries
    return entries


def build_current_dataset() -> dict[str, Any]:
    """Build tasks from the current official Moscow archive without reloading old years."""
    catalog = _fetch_current_pdf_catalog()
    task_files = [item for item in catalog if item.kind == "tasks"]
    solution_files = [item for item in catalog if item.kind == "solution"]
    solution_lookup: dict[tuple[str, str, str], list[PdfFile]] = defaultdict(list)
    for item in solution_files:
        solution_lookup[(item.season, item.stage, item.slug)].append(item)
    solution_urls = {item.url for item in solution_files}
    task_files = [
        item for item in task_files
        if _match_solution_file(item, solution_lookup, solution_urls) is not None
    ]

    entries_cache: dict[str, list[dict[str, Any]]] = {}
    tasks: list[dict[str, Any]] = []
    bucket_counts: dict[tuple[str, int], int] = defaultdict(int)
    seen: set[tuple[str, int, int | None, int, str]] = set()

    for task_file in sorted(task_files, key=lambda item: (item.slug, item.stage, item.name)):
        subject = CURRENT_SUBJECT_NAMES.get(task_file.slug) or task_file.subject_name.lower()
        if not subject:
            continue
        task_entries = _load_entries_cached(task_file.url, entries_cache)
        if not task_entries:
            continue

        solution_file = _match_solution_file(task_file, solution_lookup, solution_urls)
        solution_map: dict[tuple[int, int | None], str] = {}
        if solution_file:
            for entry in _load_entries_cached(solution_file.url, entries_cache):
                try:
                    task_number = int(entry.get("task_number"))
                except (TypeError, ValueError):
                    continue
                try:
                    variant = int(entry.get("variant")) if entry.get("variant") is not None else None
                except (TypeError, ValueError):
                    variant = None
                text = _clean_text(
                    entry.get("official_solution") or entry.get("statement"),
                    limit=16000,
                )
                if not text:
                    continue
                key = (task_number, variant)
                if len(text) > len(solution_map.get(key, "")):
                    solution_map[key] = text

        for task_entry in task_entries:
            statement = _clean_text(task_entry.get("statement"), limit=15000)
            statement = _clean_text(_VARIANT_REFERENCE_RE.sub(" ", statement), limit=15000)
            if not _looks_like_task_text(statement):
                continue
            try:
                task_number = int(task_entry.get("task_number"))
            except (TypeError, ValueError):
                continue
            try:
                variant = int(task_entry.get("variant")) if task_entry.get("variant") is not None else None
            except (TypeError, ValueError):
                variant = None

            solution_candidate = _clean_text(
                solution_map.get((task_number, variant))
                or solution_map.get((task_number, None))
                or task_entry.get("official_solution")
                or "",
                limit=15000,
            )
            answer = _extract_answer(solution_candidate)
            # Some answer-booklet PDFs repeat the questions verbatim instead of
            # providing a key. Keep them as source documents, but don't expose a
            # duplicate condition as the official solution.
            duplicate_solution = bool(
                solution_candidate and _similarity(statement, solution_candidate) >= 0.82
            )
            ambiguous_solution_key = bool(
                variant is None
                and len(_REPEATED_ANSWER_LABEL_RE.findall(solution_candidate)) > 1
            )
            official_solution = (
                "" if duplicate_solution or ambiguous_solution_key else solution_candidate
            )

            try:
                page_start = int(task_entry.get("page_start") or 0) or None
                page_end = int(task_entry.get("page_end") or 0) or page_start
            except (TypeError, ValueError):
                page_start = page_end = None
            source_fragments = _normalize_source_fragments(task_entry, page_start, page_end)
            if not source_fragments:
                continue

            statement_hash = hashlib.sha1(statement.encode("utf-8")).hexdigest()[:12]
            for grade in sorted(set(task_file.grades) & set(TARGET_GRADES)):
                identity = (task_file.url, task_number, variant, grade, statement_hash)
                if identity in seen:
                    continue
                seen.add(identity)
                bucket = (subject, grade)
                index_in_bucket = bucket_counts[bucket]
                bucket_counts[bucket] += 1
                difficulty, points = _difficulty_and_points(index_in_bucket)
                base_id = hashlib.sha1(
                    f"{task_file.url}|{task_number}|{variant}|{grade}|{statement_hash}".encode("utf-8")
                ).hexdigest()
                variant_part = f" вариант {variant}" if variant is not None else ""
                title = (
                    f"ВСОШ 2026 {grade} класс {subject} задача {task_number}{variant_part} "
                    f"({task_file.stage}) #{index_in_bucket + 1}-{base_id[:10]}"
                )
                explanation = (
                    _build_ai_explanation(statement, official_solution, answer, subject, grade)
                    if official_solution
                    else ""
                )
                tasks.append(
                    {
                        "title": title,
                        "problem_statement": statement,
                        "answer": answer,
                        "subject": subject,
                        "grade": grade,
                        "difficulty": difficulty,
                        "points": points,
                        "input_format": None,
                        "output_format": None,
                        "examples": None,
                        "solution_explanation": explanation,
                        "topic": "ВСОШ",
                        "tags": "vsosh,official-task,2026-27",
                        "time_limit": 900,
                        "attachments": [
                            {
                                "type": "pdf",
                                "title": "Оригинал условия (PDF)",
                                "pdf_url": task_file.url,
                            }
                        ],
                        "source_pdf_url": task_file.url,
                        "source_solution_pdf_url": (
                            solution_file.url
                            if solution_file and not duplicate_solution
                            else ""
                        ),
                        "source_page_start": page_start,
                        "source_page_end": page_end,
                        "source_fragments": source_fragments,
                        "full_problem_statement": statement,
                        "official_solution_text": official_solution,
                        "free_ai_explanation": explanation,
                        "free_ai_status": "ready" if explanation else "empty",
                        "ai_answer_short": None,
                        "ai_solution_full": None,
                        "ai_solution_status": "empty",
                        "ai_solution_model": None,
                        "ai_solution_error": None,
                        "ai_solution_hash": None,
                        "ai_solution_generated_at": None,
                    }
                )

    return {"tasks": tasks}


def build_dataset() -> dict[str, Any]:
    catalog = _build_catalog()
    task_files = [f for f in catalog if f.kind == "tasks"]
    solution_files = [f for f in catalog if f.kind == "solution"]

    solution_lookup: dict[tuple[str, str, str], list[PdfFile]] = defaultdict(list)
    for solution_file in solution_files:
        solution_lookup[(solution_file.season, solution_file.stage, solution_file.slug)].append(solution_file)
    all_solution_urls = {f.url for f in solution_files}

    entries_cache: dict[str, list[dict[str, Any]]] = {}
    candidate_pool: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)

    for subject_cfg in SUBJECT_CONFIGS:
        subject_name = subject_cfg["name"]
        matched_task_files = [f for f in task_files if _subject_allows_file(subject_cfg, f)]
        for task_file in matched_task_files:
            task_entries = _load_entries_cached(task_file.url, entries_cache)
            if not task_entries:
                continue

            solution_file = _match_solution_file(task_file, solution_lookup, all_solution_urls)
            solution_map: dict[int, str] = {}
            if solution_file:
                solution_entries = _load_entries_cached(solution_file.url, entries_cache)
                for entry in solution_entries:
                    try:
                        task_num = int(entry.get("task_number"))
                    except Exception:
                        continue
                    text = _clean_text(entry.get("official_solution") or entry.get("statement"), limit=16000)
                    if not text:
                        continue
                    prev = solution_map.get(task_num, "")
                    if len(text) > len(prev):
                        solution_map[task_num] = text

            for entry_index, task_entry in enumerate(task_entries, start=1):
                statement = _clean_text(task_entry.get("statement"), limit=15000)
                if not _looks_like_task_text(statement):
                    continue

                task_number = int(task_entry.get("task_number") or entry_index)
                official_solution = _clean_text(
                    solution_map.get(task_number)
                    or task_entry.get("official_solution")
                    or "",
                    limit=15000,
                )
                if len(official_solution) < 20:
                    continue

                page_start = int(task_entry.get("page_start") or 0) or None
                page_end = int(task_entry.get("page_end") or 0) or page_start
                source_fragments = _normalize_source_fragments(task_entry, page_start, page_end)
                if not source_fragments:
                    continue

                base_id_raw = (
                    f"{subject_name}|{task_file.url}|{page_start}|{page_end}|"
                    f"{task_number}|{hashlib.sha1(statement.encode('utf-8')).hexdigest()[:12]}"
                )
                base_id = hashlib.sha1(base_id_raw.encode("utf-8")).hexdigest()
                source_solution_url = solution_file.url if solution_file else ""

                base_candidate = {
                    "base_id": base_id,
                    "subject": subject_name,
                    "task_file": task_file,
                    "task_number": task_number,
                    "variant": task_entry.get("variant"),
                    "statement": statement,
                    "official_solution": official_solution,
                    "source_pdf_url": task_file.url,
                    "source_solution_pdf_url": source_solution_url,
                    "source_page_start": page_start,
                    "source_page_end": page_end,
                    "source_fragments": source_fragments,
                }

                for target_grade in TARGET_GRADES:
                    score = _candidate_score(target_grade, task_file, len(task_entries))
                    candidate = dict(base_candidate)
                    candidate["target_grade"] = target_grade
                    candidate["score"] = score
                    candidate_pool[(subject_name, target_grade)].append(candidate)

    selected_by_bucket: dict[tuple[str, int], list[dict[str, Any]]] = {}
    overflow_by_bucket: dict[tuple[str, int], list[dict[str, Any]]] = {}

    for subject_cfg in SUBJECT_CONFIGS:
        subject = subject_cfg["name"]
        for grade in TARGET_GRADES:
            key = (subject, grade)
            bucket = sorted(
                candidate_pool.get(key, []),
                key=lambda item: (
                    -item["score"],
                    -len(item["official_solution"]),
                    -len(item["statement"]),
                ),
            )
            unique: list[dict[str, Any]] = []
            seen = set()
            for item in bucket:
                dedup_key = item["base_id"]
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)
                unique.append(item)

            if len(unique) < TARGET_PER_SUBJECT_GRADE:
                raise RuntimeError(
                    f"Not enough official tasks for {subject} grade {grade}: "
                    f"{len(unique)} < {TARGET_PER_SUBJECT_GRADE}"
                )

            selected_by_bucket[key] = unique[:TARGET_PER_SUBJECT_GRADE]
            overflow_by_bucket[key] = unique[TARGET_PER_SUBJECT_GRADE:]

    tasks: list[dict[str, Any]] = []
    global_seen_titles = set()

    def append_task(candidate: dict[str, Any], index_in_bucket: int, bucket_size: int) -> None:
        subject = candidate["subject"]
        grade = int(candidate["target_grade"])
        task_file: PdfFile = candidate["task_file"]
        season_year = _season_start_year(task_file.season, task_file.year_id)
        difficulty, points = _difficulty_and_points(index_in_bucket)

        answer = _extract_answer(candidate["official_solution"])
        ai_explanation = _build_ai_explanation(
            candidate["statement"],
            candidate["official_solution"],
            answer,
            subject,
            grade,
        )

        signature = candidate["base_id"][:10]
        variant = candidate.get("variant")
        variant_part = f" вариант {variant}" if variant else ""
        title = (
            f"ВСОШ {season_year} {grade} класс {subject} "
            f"задача {candidate['task_number']}{variant_part} ({task_file.stage}) #{index_in_bucket + 1}-{signature}"
        )
        if title in global_seen_titles:
            title = f"{title}-dup"
        global_seen_titles.add(title)

        task_payload = {
            "title": title,
            "problem_statement": candidate["statement"],
            "answer": answer,
            "subject": subject,
            "grade": grade,
            "difficulty": difficulty,
            "points": points,
            "input_format": None,
            "output_format": None,
            "examples": None,
            "solution_explanation": ai_explanation,
            "topic": "ВСОШ",
            "tags": "vsosh,official-task",
            "time_limit": 900,
            "attachments": [
                {
                    "type": "pdf",
                    "title": "Оригинал условия (PDF)",
                    "pdf_url": candidate["source_pdf_url"],
                }
            ],
            "source_pdf_url": candidate["source_pdf_url"],
            "source_solution_pdf_url": candidate["source_solution_pdf_url"],
            "source_page_start": candidate["source_page_start"],
            "source_page_end": candidate["source_page_end"],
            "source_fragments": candidate["source_fragments"],
            "full_problem_statement": candidate["statement"],
            "official_solution_text": candidate["official_solution"],
            "free_ai_explanation": ai_explanation,
            "free_ai_status": "ready",
            "ai_answer_short": None,
            "ai_solution_full": None,
            "ai_solution_status": "empty",
            "ai_solution_model": None,
            "ai_solution_error": None,
            "ai_solution_hash": None,
            "ai_solution_generated_at": None,
        }
        tasks.append(task_payload)

    for subject_cfg in SUBJECT_CONFIGS:
        subject = subject_cfg["name"]
        for grade in TARGET_GRADES:
            key = (subject, grade)
            for idx, candidate in enumerate(selected_by_bucket[key]):
                append_task(candidate, idx, TARGET_PER_SUBJECT_GRADE)

    baseline_count = len(tasks)
    if baseline_count != len(SUBJECT_CONFIGS) * len(TARGET_GRADES) * TARGET_PER_SUBJECT_GRADE:
        raise RuntimeError(f"Unexpected baseline count: {baseline_count}")

    extras_needed = max(0, TARGET_TOTAL_TASKS - baseline_count)
    if extras_needed > 0:
        bucket_keys = sorted(
            overflow_by_bucket.keys(),
            key=lambda k: len(overflow_by_bucket[k]),
            reverse=True,
        )
        extra_index_by_bucket = defaultdict(int)
        added = 0
        while added < extras_needed:
            progressed = False
            for key in bucket_keys:
                idx = extra_index_by_bucket[key]
                overflow = overflow_by_bucket[key]
                if idx >= len(overflow):
                    continue
                candidate = overflow[idx]
                extra_index_by_bucket[key] += 1
                append_task(candidate, TARGET_PER_SUBJECT_GRADE + idx, TARGET_PER_SUBJECT_GRADE + 1)
                added += 1
                progressed = True
                if added >= extras_needed:
                    break
            if not progressed:
                raise RuntimeError(
                    f"Unable to reach {TARGET_TOTAL_TASKS} tasks. Built {len(tasks)} tasks."
                )

    if len(tasks) > TARGET_TOTAL_TASKS:
        tasks = tasks[:TARGET_TOTAL_TASKS]

    return {"tasks": tasks}


def _print_coverage(tasks_payload: dict[str, Any]) -> None:
    tasks = tasks_payload.get("tasks", [])
    by_bucket = defaultdict(int)
    by_subject = defaultdict(int)
    for task in tasks:
        subject = str(task.get("subject") or "")
        grade = int(task.get("grade") or 0)
        by_bucket[(subject, grade)] += 1
        by_subject[subject] += 1

    print(f"Total tasks: {len(tasks)}")
    for subject_cfg in SUBJECT_CONFIGS:
        subject = subject_cfg["name"]
        counts = [by_bucket[(subject, grade)] for grade in TARGET_GRADES]
        counts_text = ", ".join(f"{grade}:{count}" for grade, count in zip(TARGET_GRADES, counts))
        print(f"{subject}: {counts_text} | subject_total={by_subject[subject]}")


def main() -> None:
    dataset = build_dataset()
    TASKS_JSON_PATH.write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    _print_coverage(dataset)
    print(f"Written: {TASKS_JSON_PATH}")


if __name__ == "__main__":
    main()
