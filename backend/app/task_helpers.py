import hashlib
import re
from datetime import datetime, timedelta

from app.config import (
    _safe_int, _normalize_subject, _normalize_difficulty, _normalize_olympiad_name,
    _is_manual_answer, _time_limit_by_difficulty,
    SUBJECT_THEMES, MONTHS_RU_GENITIVE,
    YEAR_RE, TASK_NUMBER_RE, VARIANT_NUMBER_RE,
)
from app.utils.text import (
    normalize_text_value as _normalize_text_value,
    strip_source_lines as _strip_source_lines,
    clean_solution_explanation_text as _clean_solution_explanation_text,
)
from app.utils.answer import clean_reference_answer_text, answer_input_hint_for_reference, ANSWER_HINT_MANUAL


def infer_topic(subject: str, statement: str, fallback_task_number: str = "") -> str:
    normalized_subject = _normalize_subject(subject)
    statement_lower = _strip_source_lines(statement or "").lower()
    candidate_topics = SUBJECT_THEMES.get(normalized_subject, [])
    keyword_map = {
        "граф": "графики", "таблиц": "табличные данные", "скорост": "механика",
        "раствор": "растворы", "клетк": "клетка", "пунктуац": "пунктуация",
        "хронолог": "хронология", "климат": "климат", "экосистем": "экосистемы",
        "датчик": "датчики", "grammar": "grammar", "vocabulary": "vocabulary",
    }
    for marker, topic in keyword_map.items():
        if marker in statement_lower and (not candidate_topics or topic in candidate_topics):
            return topic
    if candidate_topics:
        checksum = sum(ord(ch) for ch in statement_lower) if statement_lower else 0
        return candidate_topics[checksum % len(candidate_topics)]
    return f"тема задачи {fallback_task_number}" if fallback_task_number else "общая тема"


def infer_answer_from_statement(statement: str):
    clean = _strip_source_lines(statement or "")
    if not clean:
        return None
    winter_match = re.search(r"первый зимний день\s*1\s*декабря.*?дат[ау]\s*(\d+)\s*дня\s*зимы", clean, re.IGNORECASE | re.DOTALL)
    if winter_match:
        day_number = _safe_int(winter_match.group(1), None)
        if day_number and day_number >= 1:
            date_value = datetime(datetime.now().year, 12, 1) + timedelta(days=day_number - 1)
            return f"{date_value.day} {MONTHS_RU_GENITIVE.get(date_value.month, '')}".strip()
    sum_match = re.search(r"сумм[ауы].*?(\d+)\s*[+]\s*(\d+)", clean, re.IGNORECASE)
    if sum_match:
        return str(_safe_int(sum_match.group(1), 0) + _safe_int(sum_match.group(2), 0))
    return None


def generate_fallback_solution(statement: str, subject: str, topic: str, answer: str, failure_reason: str = "") -> str:
    cleaned = _strip_source_lines(statement or "")
    inferred = infer_answer_from_statement(cleaned)
    final_answer = _normalize_text_value(answer)
    if _is_manual_answer(final_answer):
        final_answer = inferred or ""
    if not final_answer:
        final_answer = inferred or ""
    short = cleaned.strip()
    if len(short) > 700:
        short = f"{short[:700]}..."
    lines = [
        "Решение временно недоступно. Локальная модель не смогла сгенерировать ответ.",
        f"Предмет: {subject or 'не указан'}. Тема: {topic or 'не указана'}.",
    ]
    reason = _normalize_text_value(failure_reason or "")
    if reason:
        lines.append(f"Причина: {reason}")
    if short:
        lines.append(f"Фрагмент условия: {short}")
    lines.append(f"Итоговый ответ: {final_answer}" if final_answer else "Итоговый ответ недоступен: для точного решения нужен рабочий локальный LLM API и полный текст условия.")
    return "\n".join(lines)


def extract_variant_number(value: str):
    text = _normalize_text_value(value or "")
    if not text:
        return None
    match = VARIANT_NUMBER_RE.search(text)
    return _safe_int(match.group(1), None) if match else None


def parse_title_parts(raw_title: str):
    title = str(raw_title or "").strip()
    year_match = YEAR_RE.search(title)
    task_match = TASK_NUMBER_RE.search(title)
    year = year_match.group(1) if year_match else ""
    task_number = task_match.group(1) if task_match else ""
    olympiad_raw = title[:year_match.start()].strip() if (year_match and year_match.start() > 0) else (title.split()[0] if title else "")
    return _normalize_olympiad_name(olympiad_raw), year, task_number


def build_task_title(raw_title: str, subject: str, grade, topic: str = None, force: bool = False) -> str:
    title = str(raw_title or "").strip()
    if title and not force and not any(m in title.lower() for m in ("vsosh", "grade", "task")):
        return title
    olympiad, year, task_number = parse_title_parts(title)
    year_value = year or str(datetime.now().year)
    grade_value = f"{grade}" if grade is not None else "без"
    variant_number = extract_variant_number(title)
    variant_part = f" вариант {variant_number}" if variant_number is not None else ""
    topic_value = str(topic or "").strip()
    if topic_value.upper() == olympiad.upper():
        topic_value = ""
    if not topic_value:
        topic_value = f"задача {task_number}{variant_part}" if task_number else "общая тема"
    elif task_number:
        topic_value = f"задача {task_number}{variant_part}"
    return f"{olympiad} {year_value} {grade_value} класс {subject} {topic_value}".strip()


def task_identity_key(raw_title: str, subject: str, grade, problem_statement: str = "") -> str:
    olympiad, year, task_number = parse_title_parts(raw_title)
    normalized_subject = _normalize_subject(subject).lower()
    grade_part = "" if grade is None else str(grade)
    normalized_statement = re.sub(r"\s+", " ", _strip_source_lines(problem_statement or "").strip().lower())
    statement_hash = hashlib.sha1(normalized_statement.encode("utf-8")).hexdigest()[:12] if normalized_statement else ""
    if year and task_number:
        base = f"{olympiad.lower()}|{year}|{normalized_subject}|{grade_part}|{task_number}"
        return f"{base}|{statement_hash}" if statement_hash else base
    normalized_title = re.sub(r"\s+", " ", str(raw_title or "").strip().lower())
    base = f"{normalized_subject}|{grade_part}|{normalized_title}"
    return f"{base}|{statement_hash}" if statement_hash else base


def task_olympiad(task) -> str:
    olympiad, _, _ = parse_title_parts(task.title)
    return _normalize_olympiad_name(olympiad)


def task_list_payload(task, view_count=None):
    """Lightweight payload for task lists — truncates problem_statement, omits heavy fields."""
    raw_statement = _strip_source_lines(task.problem_statement or "")
    # Truncate for list view — full text available via /tasks/{id} endpoint
    stmt = raw_statement[:300] + ("…" if len(raw_statement) > 300 else "")
    payload = {
        "id": task.id,
        "title": build_task_title(task.title, _normalize_subject(task.subject), task.grade, task.topic),
        "problem_statement": stmt,
        "difficulty": _normalize_difficulty(task.difficulty),
        "subject": _normalize_subject(task.subject),
        "olympiad": task_olympiad(task),
        "grade": task.grade,
        "topic": task.topic,
        "tags": task.tags,
        "answer_input_hint": answer_input_hint_for_task(task),
        "points": task.points,
        "time_limit": _time_limit_by_difficulty(task.difficulty),
    }
    if view_count is not None:
        payload["view_count"] = int(view_count or 0)
    return payload


def answer_input_hint_for_task(task) -> str:
    reference_answers, manual_check = resolve_task_reference_answers(task)
    if manual_check or not reference_answers:
        return ANSWER_HINT_MANUAL
    return answer_input_hint_for_reference(reference_answers[0])


def extract_answer_from_official_solution(official_solution_text: str) -> str:
    from app.utils.text import _fix_mojibake_text
    raw_text = _fix_mojibake_text(str(official_solution_text or "")).strip()
    if not raw_text:
        return ""
    model_match = re.search(r"(?m)^модель\s+ответа?.*?$", raw_text, re.IGNORECASE)
    if model_match:
        answer_lines = []
        started = False
        for line in raw_text[model_match.end():].splitlines():
            stripped = line.strip()
            if not stripped:
                if started:
                    break
                continue
            started = True
            if re.match(r"(?:пояснение|комментарий|решение)[.:\s]", stripped, re.IGNORECASE):
                break
            val = re.sub(r"[.\s]*(?:за\s+полностью|[–—-]\s*\d+\s*балла?\s+за).*$", "", stripped, flags=re.IGNORECASE).strip().rstrip(".")
            if val:
                answer_lines.append(val)
        if answer_lines:
            return clean_reference_answer_text(" ".join(answer_lines))
    answer_match = re.search(r"(?m)^\s*(?:итоговый\s+ответ|ответ|final\s+answer)\s*[:\-]\s*(.+)$", raw_text)
    if answer_match:
        trimmed = re.split(r"\s+(?:решение|разбор|solution)[.:\s]", answer_match.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
        return clean_reference_answer_text(trimmed)
    block_match = re.search(r"(?m)^\s*(?:итоговый\s+ответ|ответ|final\s+answer)\s*[:\-]?\s*$", raw_text)
    if block_match:
        answer_lines = []
        for line in raw_text[block_match.end():].splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if re.match(r"(?:решение|разбор|solution)[.:\s]", stripped, re.IGNORECASE):
                break
            val = re.sub(r"^[\u2713\u2714\u2611\u2022\*\-]+\s*", "", stripped)
            if val and re.search(r"[0-9a-zа-яё]", val, re.IGNORECASE):
                answer_lines.append(val)
        if answer_lines:
            return clean_reference_answer_text(",".join(answer_lines))
    return clean_reference_answer_text(_normalize_text_value(raw_text))


def collect_task_reference_answers(task) -> list:
    from app.utils.answer import looks_like_meaningful_answer, normalize_compact_answer_token
    candidates = []
    ai_answer = clean_reference_answer_text(getattr(task, "ai_answer_short", "") or "")
    if ai_answer and looks_like_meaningful_answer(ai_answer) and not _is_manual_answer(ai_answer):
        candidates.append(ai_answer)
    official_answer = extract_answer_from_official_solution(getattr(task, "official_solution_text", "") or "")
    if official_answer and looks_like_meaningful_answer(official_answer) and not _is_manual_answer(official_answer):
        candidates.append(official_answer)
    if not candidates:
        fallback = clean_reference_answer_text(getattr(task, "official_solution_text", "") or "")
        if fallback and looks_like_meaningful_answer(fallback) and not _is_manual_answer(fallback):
            candidates.append(fallback)
    seen = set()
    deduped = []
    for c in candidates:
        key = normalize_compact_answer_token(c)
        if key and key not in seen:
            seen.add(key)
            deduped.append(c)
    return deduped


def resolve_task_reference_answers(task):
    candidates = collect_task_reference_answers(task)
    return (candidates, False) if candidates else ([], True)


def resolve_task_reference_answer(task):
    candidates, manual_check = resolve_task_reference_answers(task)
    return (candidates[0] if candidates else ""), manual_check


def resolve_task_ai_reference_answer(task) -> str:
    from app.utils.answer import looks_like_meaningful_answer
    ai_answer = clean_reference_answer_text(getattr(task, "ai_answer_short", "") or "")
    if ai_answer and looks_like_meaningful_answer(ai_answer) and not _is_manual_answer(ai_answer):
        return ai_answer
    return ""


def resolve_vsosh_reference_answer(task) -> str:
    from app.utils.answer import looks_like_meaningful_answer
    from app.ai_worker import _extract_answer_from_solution_text
    official_text = _normalize_text_value(getattr(task, "official_solution_text", "") or "")
    answer = extract_answer_from_official_solution(official_text)
    if answer and looks_like_meaningful_answer(answer) and not _is_manual_answer(answer):
        return answer
    fallback = _extract_answer_from_solution_text(official_text)
    if fallback and looks_like_meaningful_answer(fallback) and not _is_manual_answer(fallback):
        return fallback
    return ""





def is_task_ai_answer_pending(task) -> bool:
    from app.ai_worker import is_ai_generation_stale, is_ai_generation_job_active
    from app.config import NON_AUTORETRY_AI_STATUSES
    if resolve_task_ai_reference_answer(task):
        return False
    status = _normalize_text_value(getattr(task, "ai_solution_status", "") or "").lower()
    if status == "ready":
        return False
    if status in NON_AUTORETRY_AI_STATUSES:
        return False
    if is_ai_generation_stale(task):
        return False
    if is_ai_generation_job_active(task.id):
        return True
    return status in ("", "empty", "queued", "generating", "error", "rate_limited")


def ensure_task_ai_generation(task, db) -> str:
    from app.ai_worker import queue_ai_solution_generation
    if _normalize_text_value(getattr(task, "ai_solution_status", "") or "").lower() not in ("queued", "generating"):
        task.ai_solution_status = "queued"
        task.ai_solution_error = None
        from datetime import datetime
        task.ai_solution_generated_at = datetime.utcnow()
        db.commit()
    queued = queue_ai_solution_generation(task.id, force=False)
    return "queued" if queued else "queued_existing"


def record_task_view(task_id: int, db):
    try:
        from datetime import datetime, date
        from app.database import TaskView
        today = date.today()
        row = db.query(TaskView).filter(TaskView.task_id == task_id, TaskView.viewed_on == today).first()
        if row:
            row.view_count = (row.view_count or 0) + 1
            row.updated_at = datetime.utcnow()
        else:
            db.add(TaskView(task_id=task_id, viewed_on=today, view_count=1, updated_at=datetime.utcnow()))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Предупреждение: не удалось записать просмотр задачи (возможно, таблица task_views отсутствует): {e}")
