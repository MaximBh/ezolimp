from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any
from app.utils.safe_http import MAX_PDF_PAGES

try:
    import pypdfium2 as pdfium
except Exception:  # pragma: no cover - handled by callers
    pdfium = None


_STRONG_TASK_PATTERNS = [
    re.compile(r"^\s*(?:задача|задание|task)\s+(\d{1,3})(?:\s*[\.:]|\s+|$)", re.IGNORECASE),
    re.compile(r"^\s*(?:№|n)\s*(\d{1,3})(?:\s*[\.:]|\b|$)", re.IGNORECASE),
]
_NUMBERED_TASK_VARIANT_RE = re.compile(
    r"^\s*(?:задача|задание|task)\s+(\d{1,3})\s*[./-]\s*(\d{1,3})(?:\s*[.:)]|\s+|$)",
    re.IGNORECASE,
)
_VARIANT_RE = re.compile(
    r"^\s*(?:задача|задание|task)\s+(\d{1,3})(?:\s*[\.:])?\s*[Вв]ариант\s+(\d+)(?:\s*[\.:])?",
    re.IGNORECASE,
)
_NUMBERED_VARIANT_RE = re.compile(
    r"^\s*(?:вариант|variant)\s+(\d{1,3})\s*[./-]\s*(\d{1,3})"
    r"(?:\s*[./-]\s*(\d{1,3}))?(?:\s*[.:)]|\s+|$)",
    re.IGNORECASE,
)
_STANDALONE_VARIANT_RE = re.compile(r"^\s*[Вв]ариант\s+(\d+)(?:\s*[\.:])?", re.IGNORECASE)
_WEAK_TASK_PATTERN = re.compile(r"^\s*(\d{1,3})(?:\.\s+|\)\s*)\S")

_ANSWER_MARKER_RE = re.compile(
    r"^\s*(?:(?:итоговый)\s+)?(?:ответ|ответы|answer)\s*[:.\-–—]",
    re.IGNORECASE,
)
_INLINE_ANSWER_MARKER_RE = re.compile(
    r"(?<=[.!?])\s+(?:(?:итоговый)\s+)?(?:ответ|ответы|answer)\s*[:.\-–—]\s*",
    re.IGNORECASE,
)
_SOLUTION_START_RE = re.compile(
    r"^\s*(?:решение|разбор|official solution|solution)\s*[:\-]?\s*$",
    re.IGNORECASE,
)
_INLINE_SOLUTION_START_RE = re.compile(
    r"^\s*(?:решение|разбор|official solution|solution)\s*[:\-]\s*\S",
    re.IGNORECASE,
)
_INLINE_POINTS_MARKER_RE = re.compile(
    r"(\d{1,2}\s+балл(?:а|ов)?\s*\(\s*\d{1,2}\s+балл(?:а|ов)?\s*\))",
    re.IGNORECASE,
)
_HEADER_NOISE_RE = re.compile(
    r"(?:всероссийская олимпиада школьников|пригласительный этап|школьный этап|муниципальный этап|"
    r"региональный этап|заключительный этап|max|максимальное количество баллов)\b",
    re.IGNORECASE,
)
_ACADEMIC_YEAR_RE = re.compile(r"\b20\d{2}\s*[–-]\s*20\d{2}\s*уч\.?\s*г\.?", re.IGNORECASE)
_CITY_DATE_RE = re.compile(
    r"^\s*(?:г\.\s*)?[А-ЯЁ][А-ЯЁа-яё\-\s]{1,48},?\s*\d{1,2}\s+"
    r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)"
    r"\s+20\d{2}(?:\s*г(?:ода|\.)?)?\s*$",
    re.IGNORECASE,
)
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")
_PAGE_FOOTER_RE = re.compile(r"^\s*(?:страница|page)\s+\d+\s+(?:из|of)\s+\d+\s*$", re.IGNORECASE)
_PAGE_ARTIFACT_RE = re.compile(
    r"(?:\b(?:страница|page)\s+\d{1,4}\s+(?:из|of)\s+\d{1,4}\b|"
    r"\bпервая\s+группа\s+регионов\b|"
    r"\bобразовательный\s+центр\s+[«\"']?сириус[»\"']?,?\s+\d{1,2}\s+"
    r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+20\d{2}\b)",
    re.IGNORECASE,
)
_SIRIUS_HEADER_RE = re.compile(
    r"^\s*образовательный\s+центр\s+[«\"']?сириус[»\"']?,?\s+\d{1,2}\s+"
    r"(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+20\d{2}\s*$",
    re.IGNORECASE,
)
_SIRIUS_GROUP_HEADER_RE = re.compile(r"^\s*первая\s+группа\s+регионов\s*$", re.IGNORECASE)
_TASK_ONLY_HEADER_RE = re.compile(r"^\s*(?:задача|задание|task)\s+\d{1,3}\s*[.:]?\s*$", re.IGNORECASE)
_SCORING_HEADER_RE = re.compile(
    r"^\s*(?:всего\s+\d+\s+балл(?:а|ов)?|максимальн(?:ый|ое)\s+(?:балл|количество баллов))\b",
    re.IGNORECASE,
)
_SCORING_NOTE_RE = re.compile(
    r"^\s*(?:если\s+не\s+указан(?:\s+один\s+из)?\s+ответ(?:а|ов)?|за\s+верный\s+ответ)\b",
    re.IGNORECASE,
)
_INVALID_PDF_TEXT_RE = re.compile(r"[\uFFFE\uFFFF]")
_PYTHON_CONTROL_RE = re.compile(
    r"^(?:import|from|for|while|if|elif|else|def|class|return|print|break|continue|pass|raise|try|with|async)\b",
    re.IGNORECASE,
)
_CPP_CONTROL_RE = re.compile(
    r"^(?:#include|using\b|int\b|long\b|unsigned\b|signed\b|auto\b|bool\b|void\b|char\b|short\b|double\b|float\b|size_t\b|vector\b|multiset\b|cout\b|cin\b)",
    re.IGNORECASE,
)
_CPP_FOR_RE = re.compile(r"^for\s*\([^;]*;[^;]*;", re.IGNORECASE)
_CPP_CONTINUATION_RE = re.compile(r"^(?:\+|\*|/|%|&&|\|\||<<|>>|\?)\s*(?:[A-Za-z_(0-9]|$)")
_CPP_BROKEN_INCREMENT_RE = re.compile(r"^(?:[+\-−]\s*[+\-−])\s*[A-Za-z_]\s*(?:[A-Za-z_0-9]\s*)*;?$")
_SPACED_CPP_LINE_RE = re.compile(r"(?:\b[A-Za-z]\s+){2,}[A-Za-z]\b.*[<>{};=()]|[<>{};=()].*(?:\b[A-Za-z]\s+){2,}[A-Za-z]\b")
_SPACED_CPP_TOKENS = (
    "upper_bound", "push_back", "multiset", "namespace", "include", "vector", "rbegin", "rend",
    "begin", "erase", "insert", "sort", "using", "long", "size_t", "auto", "bool", "int",
    "cin", "cout", "endl", "for", "if", "else", "ans", "possible", "prev", "it", "std",
)
_SPACED_CPP_TOKEN_RES = tuple(
    (
        token,
        re.compile(
            r"(?<![A-Za-z0-9_])" + r"\s*".join(re.escape(char) for char in token) + r"(?![A-Za-z0-9_])",
            re.IGNORECASE,
        ),
    )
    for token in _SPACED_CPP_TOKENS
)
_PYTHON_OPERATORS_RE = re.compile(r"(?:==|!=|<=|>=|\+=|-=|\*=|//=|\*\*=|(?<![<>=!])=(?!=)|[()\[\]{}.:])")

_CACHE: dict[tuple[str, int, int], list[dict[str, Any]]] = {}


def _normalize_text(value: str) -> str:
    text = _INVALID_PDF_TEXT_RE.sub("", str(value or "")).strip().lower()
    text = re.sub(r"[^a-zа-яё0-9]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(left: str, right: str) -> float:
    left_norm = _normalize_text(left)
    right_norm = _normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm:
        return 0.95
    ratio = difflib.SequenceMatcher(None, left_norm, right_norm).ratio()
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    overlap = 0.0
    if left_tokens and right_tokens:
        overlap = len(left_tokens & right_tokens) / max(len(left_tokens), 1)
    return max(ratio, 0.45 * ratio + 0.55 * overlap)


def _statement_strength(value: str) -> int:
    return len(_normalize_text(value or ""))


def _strip_page_artifacts(value: str) -> str:
    text = str(value or "").strip()
    if len(text) > 280 or not _PAGE_ARTIFACT_RE.search(text):
        return text
    text = _PAGE_ARTIFACT_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", text).strip(" \t,.:;–—-")


def _is_noise_line(line: str) -> bool:
    clean = _strip_page_artifacts(str(line or "").strip())
    if not clean:
        return True
    if _PAGE_NUMBER_RE.match(clean):
        return True
    if _PAGE_FOOTER_RE.match(clean) or _SIRIUS_HEADER_RE.match(clean) or _SIRIUS_GROUP_HEADER_RE.match(clean):
        return True
    if _SCORING_HEADER_RE.match(clean) or _SCORING_NOTE_RE.match(clean):
        return True
    if _HEADER_NOISE_RE.search(clean):
        if len(clean) <= 180 and "?" not in clean:
            return True
    lowered = clean.lower()
    if _ACADEMIC_YEAR_RE.search(clean) and "этап" in lowered and "класс" in lowered:
        if len(clean) <= 220 and "?" not in clean:
            return True
    if _ACADEMIC_YEAR_RE.search(clean) and ("уч." in lowered or "год" in lowered):
        if len(clean) <= 220 and "?" not in clean:
            return True
    if "олимпиад" in lowered and "этап" in lowered and "класс" in lowered:
        if len(clean) <= 220 and "?" not in clean:
            return True
    if "уч. г." in lowered and "этап" in lowered:
        if len(clean) <= 220 and "?" not in clean:
            return True
    if _CITY_DATE_RE.match(clean):
        if len(clean) <= 120 and "?" not in clean:
            return True
    return False


def _looks_like_python_code(line: str) -> bool:
    value = str(line or "").strip()
    if not value or len(value) > 320:
        return False
    if _PYTHON_CONTROL_RE.match(value):
        return True
    if re.match(r"^(?:i\s+f|f\s+o\s+r|w\s+h\s+i\s+l\s+e|e\s+l\s+i\s+f|e\s+l\s+s\s+e)\b", value, re.IGNORECASE):
        return True
    if value.startswith("#"):
        return True
    if re.search(r"[А-Яа-яЁё]", value):
        return False
    if re.match(r"^[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*\s*(?:\+=|-=|\*=|//=|\*\*=|=(?!=))\s*\S", value):
        return True
    return bool(
        re.match(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*\(", value)
        or re.search(r"(?:\.[ \t]*[A-Za-z](?:\s+[A-Za-z]){1,}\s*\()", value)
        or (re.search(r"[=<>!+*/%]|[()\[\].,:]", value) and re.fullmatch(r"[A-Za-z0-9_\s.,+*/%<>=!:\-−∗()\[\]{}'\"#]+", value))
    )


def _normalize_spaced_cpp_line(line: str) -> str:
    value = str(line or "").replace("−", "-").replace("∗", "*")
    for token, token_re in _SPACED_CPP_TOKEN_RES:
        value = token_re.sub(token, value)
    value = re.sub(r"(?<!\w)([+\-])\s+\1", r"\1\1", value)
    value = re.sub(r"\s*([.()\[\]])\s*", r"\1", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    return value


def _looks_like_cpp_code(line: str) -> bool:
    value = _normalize_spaced_cpp_line(str(line or "").strip()).strip()
    if not value or len(value) > 320:
        return False
    if value in {"{", "}"} or value.startswith(("++", "--")):
        return True
    if _CPP_BROKEN_INCREMENT_RE.match(value):
        return True
    if _CPP_CONTROL_RE.match(value) or _CPP_FOR_RE.match(value) or re.match(r"^(?:if|while|else|return|break)\b", value):
        return True
    if _CPP_CONTINUATION_RE.match(value):
        return True
    if re.match(r"^[A-Za-z_]\w*(?:\s*(?:\[[^\]]*\]|\.[A-Za-z_]\w*|->[A-Za-z_]\w*))*\s*(?:=|\+=|-=|\*=|/=|\+\+|--)", value):
        return True
    if re.search(r"[А-Яа-яЁё]", value):
        return False
    return bool(re.match(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\s*(?:\(|<<|>>)", value))


def _looks_like_source_code(line: str) -> bool:
    return _looks_like_python_code(line) or _looks_like_cpp_code(line)


def _looks_like_pdf_code_candidate(line: str) -> bool:
    value = _normalize_spaced_cpp_line(str(line or "").strip())
    if _looks_like_source_code(value):
        return True
    if not value or len(value) > 320 or re.search(r"[А-Яа-яЁё]", value):
        return False
    punctuation = re.findall(r"[=;{}<>\[\]()]", value)
    return len(punctuation) >= 2 or bool(re.search(r"(?:<<|>>)", value))


def _repair_spaced_pdf_code_line(text_page, page_text: str, start_index: int, line: str, page_width: float) -> str:
    """Join PDFium's synthetic spaces between glyphs in monospaced code text."""
    if not (_looks_like_pdf_code_candidate(line) or _SPACED_CPP_LINE_RE.search(line)):
        return line
    chars = list(line)
    threshold = min(5.2, max(3.2, page_width * 0.009))
    remove = set()
    for index, char in enumerate(chars):
        if char != " ":
            continue
        previous = index - 1
        following = index + 1
        while previous >= 0 and chars[previous].isspace():
            previous -= 1
        while following < len(chars) and chars[following].isspace():
            following += 1
        if previous < 0 or following >= len(chars):
            continue
        try:
            previous_box = text_page.get_charbox(start_index + previous)
            next_box = text_page.get_charbox(start_index + following)
            gap = float(next_box[0]) - float(previous_box[2])
        except Exception:
            continue
        if gap <= threshold:
            remove.update(range(index, following))
    repaired = "".join(char for index, char in enumerate(chars) if index not in remove)
    repaired = re.sub(r"\s*([.()\[\]])\s*", r"\1", repaired)
    repaired = re.sub(r"\s*,\s*", ", ", repaired)
    repaired = re.sub(r"([)\]\}])(and|or|in|is|not)\b", r"\1 \2", repaired)
    repaired = repaired.replace("×", "*")
    return _normalize_spaced_cpp_line(repaired)


def _space_python_operators(line: str) -> str:
    parts = re.split(r'("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|#.*$)', line)
    operator_re = re.compile(r"\s*(//|\*\*|==|!=|<=|>=|\+=|-=|\*=|/=|%=|=(?!=)|[+*/%<>])\s*")
    for index in range(0, len(parts), 2):
        parts[index] = operator_re.sub(r" \1 ", parts[index]).strip()
        parts[index] = re.sub(r"(?<=[\w)\]])\s*-\s*(?=\w)", " - ", parts[index])
        parts[index] = re.sub(r"\s*:\s*$", ":", parts[index])
    return "".join(parts)


def _solution_with_code_blocks(lines: list[dict[str, Any] | str]) -> str:
    records = []
    for item in lines:
        if isinstance(item, dict):
            text = _strip_page_artifacts(str(item.get("text") or "").strip())
            bbox = item.get("bbox")
        else:
            text = _strip_page_artifacts(str(item or "").strip())
            bbox = None
        records.append({"text": text, "bbox": bbox})

    spans: list[tuple[int, int]] = []
    span_start = None
    for index, item in enumerate(records):
        if _looks_like_source_code(item["text"]):
            if span_start is None:
                span_start = index
        elif item["text"]:
            if span_start is not None:
                spans.append((span_start, index))
                span_start = None
        elif span_start is not None and index + 1 < len(records) and _looks_like_source_code(records[index + 1]["text"]):
            continue
        elif span_start is not None:
            spans.append((span_start, index))
            span_start = None
    if span_start is not None:
        spans.append((span_start, len(records)))

    code_spans = []
    for start, end in spans:
        code_lines = [item for item in records[start:end] if item["text"]]
        has_control_flow = any(
            _PYTHON_CONTROL_RE.match(item["text"])
            or _CPP_FOR_RE.match(_normalize_spaced_cpp_line(item["text"]))
            or re.match(r"^(?:for|if|while|else|return|break)\b", item["text"])
            for item in code_lines
        )
        if len(code_lines) >= 3 and (has_control_flow or len(code_lines) >= 6):
            code_spans.append((start, end))

    replacements = {}
    for start, end in code_spans:
        code_records = [item for item in records[start:end] if item["text"]]
        language = "cpp" if any(
            _CPP_CONTROL_RE.match(_normalize_spaced_cpp_line(item["text"]))
            or _CPP_FOR_RE.match(_normalize_spaced_cpp_line(item["text"]))
            or re.match(r"^(?:std::|switch\s*\(|cout\b|cin\b)", _normalize_spaced_cpp_line(item["text"]))
            for item in code_records
        ) else "python"
        x_positions = sorted({
            float(item["bbox"][0]) for item in code_records
            if isinstance(item.get("bbox"), (list, tuple)) and len(item["bbox"]) >= 1
        })
        deltas = [right - left for left, right in zip(x_positions, x_positions[1:]) if right - left >= 0.008]
        indent_step = sorted(deltas)[len(deltas) // 2] if deltas else None
        base_x = min(x_positions) if x_positions else None
        formatted = []
        for item in records[start:end]:
            if not item["text"]:
                formatted.append("")
                continue
            indent = 0
            bbox = item.get("bbox")
            if indent_step and base_x is not None and isinstance(bbox, (list, tuple)) and len(bbox) >= 1:
                indent = max(0, round((float(bbox[0]) - base_x) / indent_step)) * 4
            code_line = _normalize_spaced_cpp_line(item["text"]) if language == "cpp" else _space_python_operators(item["text"])
            if language == "cpp":
                code_line = re.sub(r"^(#include)\s*<\s*([^>]+?)\s*>", r"\1<\2>", code_line)
                code_line = re.sub(r"\b(vector|multiset)\s*<\s*([^>]+?)\s*>", r"\1<\2>", code_line)
                code_line = re.sub(r"\s*;\s*", "; ", code_line).rstrip()
            formatted.append(" " * min(indent, 40) + code_line)
        replacements[start] = f"```{language}\n" + "\n".join(formatted).rstrip() + "\n```"

    result = []
    index = 0
    while index < len(records):
        if index in replacements:
            result.append(replacements[index])
            end = next(end for start, end in code_spans if start == index)
            index = end
        else:
            result.append(records[index]["text"])
            index += 1
    return "\n".join(result).strip()


def _split_statement_and_solution(lines: list[dict[str, Any] | str]) -> tuple[str, str]:
    statement_lines: list[dict[str, Any]] = []
    solution_lines: list[dict[str, Any]] = []
    in_solution = False

    for item in lines:
        raw_line = item.get("text") if isinstance(item, dict) else item
        bbox = item.get("bbox") if isinstance(item, dict) else None
        line = str(raw_line or "").strip()
        if not line:
            if in_solution:
                if solution_lines and solution_lines[-1]["text"] != "":
                    solution_lines.append({"text": "", "bbox": None})
            else:
                if statement_lines and statement_lines[-1]["text"] != "":
                    statement_lines.append({"text": "", "bbox": None})
            continue

        if not in_solution and (_ANSWER_MARKER_RE.match(line) or _SOLUTION_START_RE.match(line)):
            in_solution = True
            solution_lines.append({"text": line, "bbox": bbox})
            continue

        if not in_solution and _INLINE_SOLUTION_START_RE.match(line):
            in_solution = True
            solution_lines.append({"text": line, "bbox": bbox})
            continue

        if not in_solution:
            answer_marker = _INLINE_ANSWER_MARKER_RE.search(line)
            if answer_marker:
                statement_part = line[:answer_marker.start()].strip()
                answer_part = line[answer_marker.end():].strip()
                if statement_part:
                    statement_lines.append({"text": statement_part, "bbox": bbox})
                solution_lines.append({"text": f"Ответ: {answer_part}".strip(), "bbox": bbox})
                in_solution = True
                continue

        if in_solution:
            solution_lines.append({"text": line, "bbox": bbox})
        else:
            statement_lines.append({"text": line, "bbox": bbox})

    statement = _solution_with_code_blocks(statement_lines)
    solution = _solution_with_code_blocks(solution_lines)
    return statement, solution


def _clamp_ratio(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _char_range_bbox_ratio(
    text_page,
    text: str,
    start_index: int,
    end_index: int,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float] | None:
    if page_width <= 0 or page_height <= 0:
        return None
    if start_index < 0:
        start_index = 0
    if end_index <= start_index:
        return None

    max_index = min(len(text), int(text_page.count_chars()))
    if start_index >= max_index:
        return None
    end_index = min(end_index, max_index)

    left = None
    right = None
    bottom = None
    top = None

    for char_index in range(start_index, end_index):
        char_value = text[char_index]
        if char_value in {"\r", "\n"}:
            continue
        try:
            x0, y0, x1, y1 = text_page.get_charbox(char_index)
        except Exception:
            continue

        char_left = min(float(x0), float(x1))
        char_right = max(float(x0), float(x1))
        char_bottom = min(float(y0), float(y1))
        char_top = max(float(y0), float(y1))
        if char_right <= char_left or char_top <= char_bottom:
            continue

        left = char_left if left is None else min(left, char_left)
        right = char_right if right is None else max(right, char_right)
        bottom = char_bottom if bottom is None else min(bottom, char_bottom)
        top = char_top if top is None else max(top, char_top)

    if left is None or right is None or bottom is None or top is None:
        return None

    ratio_left = _clamp_ratio(left / page_width)
    ratio_right = _clamp_ratio(right / page_width)
    ratio_top = _clamp_ratio(1.0 - (top / page_height))
    ratio_bottom = _clamp_ratio(1.0 - (bottom / page_height))
    if ratio_right <= ratio_left or ratio_bottom <= ratio_top:
        return None
    return ratio_left, ratio_top, ratio_right, ratio_bottom


def _char_boxes_bbox_ratio(
    text_page,
    start_index: int,
    count: int,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float] | None:
    if page_width <= 0 or page_height <= 0 or start_index < 0 or count <= 0:
        return None
    try:
        end_index = min(start_index + count, int(text_page.count_chars()))
    except Exception:
        return None
    left = right = bottom = top = None
    for char_index in range(start_index, end_index):
        try:
            x0, y0, x1, y1 = text_page.get_charbox(char_index)
        except Exception:
            continue
        char_left, char_right = min(float(x0), float(x1)), max(float(x0), float(x1))
        char_bottom, char_top = min(float(y0), float(y1)), max(float(y0), float(y1))
        if char_right <= char_left or char_top <= char_bottom:
            continue
        left = char_left if left is None else min(left, char_left)
        right = char_right if right is None else max(right, char_right)
        bottom = char_bottom if bottom is None else min(bottom, char_bottom)
        top = char_top if top is None else max(top, char_top)
    if any(value is None for value in (left, right, bottom, top)):
        return None
    ratio_left = _clamp_ratio(left / page_width)
    ratio_right = _clamp_ratio(right / page_width)
    ratio_top = _clamp_ratio(1.0 - (top / page_height))
    ratio_bottom = _clamp_ratio(1.0 - (bottom / page_height))
    if ratio_right <= ratio_left or ratio_bottom <= ratio_top:
        return None
    return ratio_left, ratio_top, ratio_right, ratio_bottom


def _searched_line_bbox_ratio(
    text_page,
    query: str,
    expected_start: int,
    page_width: float,
    page_height: float,
) -> tuple[float, float, float, float] | None:
    if not query.strip():
        return None
    try:
        searcher = text_page.search(query, match_case=False)
    except Exception:
        return None
    hits = []
    try:
        hit = searcher.get_next()
        while hit:
            try:
                start_index, count = int(hit[0]), int(hit[1])
                hits.append((abs(start_index - expected_start), start_index, count))
            except Exception:
                pass
            hit = searcher.get_next()
    except Exception:
        return None
    finally:
        searcher.close()
    if not hits:
        return None
    _, start_index, count = min(hits, key=lambda item: item[0])
    return _char_boxes_bbox_ratio(text_page, start_index, count, page_width, page_height)


def _split_flattened_line_ranges(line_text: str) -> list[tuple[int, int, bool]]:
    text = str(line_text or "")
    if len(text) < 900:
        return [(0, len(text), False)]

    markers = list(_INLINE_POINTS_MARKER_RE.finditer(text))
    if len(markers) < 2:
        return [(0, len(text), False)]

    boundaries = [0]
    for marker in markers[1:]:
        boundaries.append(marker.start(1))
    boundaries.append(len(text))

    ranges: list[tuple[int, int, bool]] = []
    for idx in range(len(boundaries) - 1):
        start = boundaries[idx]
        end = boundaries[idx + 1]
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end - start < 40:
            continue
        ranges.append((start, end, True))

    if len(ranges) < 2:
        return [(0, len(text), False)]
    return ranges


def _extract_page_lines(text_page, text: str, page_width: float, page_height: float) -> list[dict[str, Any]]:
    if not text:
        return []

    records: list[dict[str, Any]] = []
    cursor = 0
    for line_with_break in text.splitlines(keepends=True):
        line_text = line_with_break.rstrip("\r\n")
        line_start = cursor
        line_ranges = _split_flattened_line_ranges(line_text)
        for sub_start, sub_end, question_start in line_ranges:
            global_start = line_start + sub_start
            global_end = line_start + sub_end
            sub_text = line_text[sub_start:sub_end]
            line_bbox = _searched_line_bbox_ratio(
                text_page,
                sub_text,
                global_start,
                page_width,
                page_height,
            )
            if line_bbox is None:
                line_bbox = _char_range_bbox_ratio(
                    text_page,
                    text,
                    global_start,
                    global_end,
                    page_width,
                    page_height,
                )
            records.append(
                {
                    "text": _repair_spaced_pdf_code_line(text_page, text, global_start, sub_text, page_width),
                    "bbox": line_bbox,
                    "question_start": bool(question_start),
                    "source_order": len(records),
                }
            )
        cursor += len(line_with_break)

    if cursor < len(text):
        line_text = text[cursor:]
        line_ranges = _split_flattened_line_ranges(line_text)
        for sub_start, sub_end, question_start in line_ranges:
            global_start = cursor + sub_start
            global_end = cursor + sub_end
            sub_text = line_text[sub_start:sub_end]
            line_bbox = _searched_line_bbox_ratio(
                text_page,
                sub_text,
                global_start,
                page_width,
                page_height,
            )
            if line_bbox is None:
                line_bbox = _char_range_bbox_ratio(
                    text_page,
                    text,
                    global_start,
                    global_end,
                    page_width,
                    page_height,
                )
            records.append(
                {
                    "text": _repair_spaced_pdf_code_line(text_page, text, global_start, sub_text, page_width),
                    "bbox": line_bbox,
                    "question_start": bool(question_start),
                    "source_order": len(records),
                }
            )

    positioned = [(index, record) for index, record in enumerate(records) if record.get("bbox")]
    if positioned:
        def reading_position(index: int, record: dict[str, Any]) -> tuple[float, float, int]:
            bbox = record.get("bbox")
            if bbox:
                return bbox[1], bbox[0], index
            before = next(((i, item["bbox"]) for i, item in reversed(positioned) if i < index), None)
            after = next(((i, item["bbox"]) for i, item in positioned if i > index), None)
            if before and after:
                distance = after[0] - before[0]
                fraction = (index - before[0]) / distance if distance else 0.5
                top = before[1][1] + (after[1][1] - before[1][1]) * fraction
                left = before[1][0] + (after[1][0] - before[1][0]) * fraction
                return top, left, index
            if after:
                return after[1][1] - 0.0001, after[1][0], index
            if before:
                return before[1][1] + 0.0001, before[1][0], index
            return float(index), 0.0, index

        positions = {
            record["source_order"]: reading_position(record["source_order"], record)
            for record in records
        }
        records.sort(key=lambda record: positions[record["source_order"]])

        rows: list[list[dict[str, Any]]] = []
        row_bottom = -1.0
        for record in records:
            bbox = record.get("bbox")
            top = positions[record["source_order"]][0]
            bottom = bbox[3] if bbox else top
            if not rows or top > row_bottom + 0.003:
                rows.append([record])
                row_bottom = bottom
            else:
                rows[-1].append(record)
                row_bottom = max(row_bottom, bottom)

        records = [
            record
            for row in rows
            for record in sorted(
                row,
                key=lambda item: (
                    item["bbox"][0] if item.get("bbox") else positions[item["source_order"]][1],
                    item["source_order"],
                ),
            )
        ]
    for record in records:
        record.pop("source_order", None)
    return records


def _merge_ratio_boxes(boxes: list[tuple[float, float, float, float]]):
    if not boxes:
        return None
    left = min(box[0] for box in boxes)
    top = min(box[1] for box in boxes)
    right = max(box[2] for box in boxes)
    bottom = max(box[3] for box in boxes)

    # Small padding so we don't trim punctuation/superscripts at the edges.
    pad_x = 0.006
    pad_y = 0.008
    left = _clamp_ratio(left - pad_x)
    top = _clamp_ratio(top - pad_y)
    right = _clamp_ratio(right + pad_x)
    bottom = _clamp_ratio(bottom + pad_y)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _entry_source_fragments(entry: dict[str, Any]) -> list[dict[str, Any]]:
    line_boxes_by_page = entry.get("line_boxes_by_page") or {}
    fragments: list[dict[str, Any]] = []
    order_index = 1

    if isinstance(line_boxes_by_page, dict):
        for page_num in sorted(line_boxes_by_page):
            try:
                page_int = int(page_num)
            except Exception:
                continue
            page_boxes = line_boxes_by_page.get(page_num) or []
            merged = _merge_ratio_boxes(page_boxes)
            if not merged:
                continue
            left, top, right, bottom = merged
            fragments.append(
                {
                    "page": page_int,
                    "x": left,
                    "y": top,
                    "width": right - left,
                    "height": bottom - top,
                    "unit": "ratio",
                    "order_index": order_index,
                }
            )
            order_index += 1

    if fragments:
        return fragments

    page_start = int(entry.get("page_start") or 0)
    page_end = int(entry.get("page_end") or page_start)
    if page_start <= 0 or page_end < page_start:
        return []

    fallback = []
    order_index = 1
    for page_num in range(page_start, page_end + 1):
        fallback.append(
            {
                "page": page_num,
                "x": 0.0,
                "y": 0.0,
                "width": 1.0,
                "height": 1.0,
                "unit": "ratio",
                "order_index": order_index,
            }
        )
        order_index += 1
    return fallback


def _extract_pages(pdf_path: Path) -> list[dict[str, Any]]:
    if pdfium is None:
        raise RuntimeError("pypdfium2 is not installed")

    document = pdfium.PdfDocument(str(pdf_path))
    pages: list[dict[str, Any]] = []
    try:
        if len(document) > MAX_PDF_PAGES:
            raise RuntimeError("PDF exceeds the page limit")
        for page_index in range(len(document)):
            page = document[page_index]
            text_page = page.get_textpage()
            try:
                text = text_page.get_text_range() or ""
                width, height = page.get_size()
                line_records = _extract_page_lines(text_page, text, width, height)
            finally:
                text_page.close()
            pages.append(
                {
                    "page": page_index + 1,
                    "text": text,
                    "lines": line_records,
                    "width": width,
                    "height": height,
                }
            )
            page.close()
    finally:
        document.close()
    return pages


def _detect_entries(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    previous_clean = ""

    def flush_current() -> None:
        nonlocal current
        if not current:
            return
        statement, official_solution = _split_statement_and_solution(current["lines"])
        if statement:
            current["statement"] = statement
            current["official_solution"] = official_solution
            current["source_fragments"] = _entry_source_fragments(current)
            entries.append(current)
        current = None

    for page_data in pages:
        page_num = int(page_data.get("page") or 0)
        page_lines = page_data.get("lines")
        if isinstance(page_lines, list) and page_lines:
            line_records = page_lines
        else:
            line_records = [{"text": line} for line in str(page_data.get("text") or "").splitlines()]

        for line_index, line_item in enumerate(line_records):
            if isinstance(line_item, dict):
                raw_line = line_item.get("text")
                line_bbox = line_item.get("bbox")
                question_start = bool(line_item.get("question_start"))
            else:
                raw_line = line_item
                line_bbox = None
                question_start = False

            clean = _strip_page_artifacts(_INVALID_PDF_TEXT_RE.sub("", str(raw_line or "")).strip())
            if _TASK_ONLY_HEADER_RE.match(clean):
                next_clean = ""
                for next_item in line_records[line_index + 1:line_index + 3]:
                    if isinstance(next_item, dict):
                        next_clean = str(next_item.get("text") or "").strip()
                    else:
                        next_clean = str(next_item or "").strip()
                    if next_clean:
                        break
                if _SCORING_HEADER_RE.match(next_clean):
                    previous_clean = clean
                    continue
            if _is_noise_line(clean):
                previous_clean = clean
                continue

            matched_number: int | None = None
            matched_variant: int | None = None

            numbered_task = _NUMBERED_TASK_VARIANT_RE.match(clean)
            numbered_variant = _NUMBERED_VARIANT_RE.match(clean)
            vm = _VARIANT_RE.match(clean)
            if numbered_task:
                matched_number = int(numbered_task.group(1))
                matched_variant = int(numbered_task.group(2))
            elif numbered_variant:
                first_number = int(numbered_variant.group(1))
                second_number = int(numbered_variant.group(2))
                last_number = int(numbered_variant.group(3) or second_number)
                current_task_number = current.get("task_number") if current else None
                if numbered_variant.group(3) and current_task_number == second_number:
                    matched_number = second_number
                else:
                    matched_number = first_number
                matched_variant = last_number
                if numbered_variant.group(3):
                    suffix = clean[numbered_variant.end():].lstrip(" .:)")
                    clean = f"Вариант {matched_number}.{matched_variant}. {suffix}".rstrip()
            elif vm:
                matched_number = int(vm.group(1))
                matched_variant = int(vm.group(2))
            else:
                for pattern in _STRONG_TASK_PATTERNS:
                    match = pattern.match(clean)
                    if match:
                        matched_number = int(match.group(1))
                        break

            if matched_number is None:
                weak = _WEAK_TASK_PATTERN.match(clean)
                if weak:
                    weak_number = int(weak.group(1))
                    current_task_number = current.get("task_number") if current else None
                    starts_at_margin = bool(
                        isinstance(line_bbox, (list, tuple))
                        and len(line_bbox) >= 1
                        and float(line_bbox[0]) <= 0.085
                    )
                    if current_task_number is None:
                        if not previous_clean or _is_noise_line(previous_clean):
                            matched_number = weak_number
                    elif (
                        current.get("variant") is None
                        and weak_number > int(current_task_number)
                        and starts_at_margin
                    ):
                        previous_numbered_line = next(
                            (
                                str(item.get("text") if isinstance(item, dict) else item).strip()
                                for item in reversed(current.get("lines") or [])
                                if str(item).strip()
                            ),
                            "",
                        )
                        previous_weak = _WEAK_TASK_PATTERN.match(previous_numbered_line)
                        continues_numbered_list = bool(
                            previous_weak and weak_number == int(previous_weak.group(1)) + 1
                        )
                        # Weakly labelled tasks such as "16) ..." are common
                        # in PDFs. Use their left margin to distinguish task
                        # headings from indented numbered options in a problem.
                        if not continues_numbered_list:
                            matched_number = weak_number

            if matched_number is None and current:
                standalone_variant = _STANDALONE_VARIANT_RE.match(clean)
                if standalone_variant:
                    variant_number = int(standalone_variant.group(1))
                    current_variant = current.get("variant")
                    current_task_number = current.get("task_number")
                    if current_variant is None:
                        current["variant"] = variant_number
                    elif current_task_number is not None and int(current_variant) != variant_number:
                        matched_number = int(current_task_number)
                        matched_variant = variant_number

            should_start_new = matched_number is not None or (
                question_start and current is not None and current.get("variant") is None
            )

            if should_start_new:
                flush_current()
                current = {
                    "task_number": matched_number,
                    "variant": matched_variant,
                    "page_start": page_num,
                    "page_end": page_num,
                    "lines": [{"text": clean, "bbox": line_bbox}],
                    "line_boxes_by_page": {page_num: [line_bbox]} if line_bbox else {},
                }
            elif current is None:
                current = {
                    "task_number": None,
                    "variant": None,
                    "page_start": page_num,
                    "page_end": page_num,
                    "lines": [{"text": clean, "bbox": line_bbox}],
                    "line_boxes_by_page": {page_num: [line_bbox]} if line_bbox else {},
                }
            else:
                current["page_end"] = page_num
                current["lines"].append({"text": clean, "bbox": line_bbox})
                if line_bbox:
                    page_boxes = current.setdefault("line_boxes_by_page", {}).setdefault(page_num, [])
                    page_boxes.append(line_bbox)

            previous_clean = clean

    flush_current()

    for index, entry in enumerate(entries, start=1):
        statement = str(entry.get("statement") or "")
        entry["index"] = index
        entry["statement_norm"] = _normalize_text(statement)
        entry.pop("line_boxes_by_page", None)
    return entries


def _load_entries(pdf_path: Path) -> list[dict[str, Any]]:
    stat = pdf_path.stat()
    key = (str(pdf_path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    pages = _extract_pages(pdf_path)
    entries = _detect_entries(pages)
    # Keep a small multi-file cache to avoid reparsing the same PDFs
    # when switching between tasks and solution documents.
    if len(_CACHE) >= 24:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = entries
    return entries


def extract_task_entries(pdf_path: Path) -> list[dict[str, Any]]:
    entries = _load_entries(pdf_path)
    result: list[dict[str, Any]] = []
    for entry in entries:
        result.append(
            {
                "task_number": entry.get("task_number"),
                "variant": entry.get("variant"),
                "index": entry.get("index"),
                "full_problem_statement": str(entry.get("statement") or "").strip(),
                "official_solution_text": str(entry.get("official_solution") or "").strip(),
                "source_page_start": int(entry.get("page_start") or 0) or None,
                "source_page_end": int(entry.get("page_end") or 0) or None,
                "source_fragments": entry.get("source_fragments") or [],
            }
        )
    return result


def extract_best_task_entry(
    pdf_path: Path,
    task_number: int | None = None,
    variant_number: int | None = None,
    statement_hint: str = "",
) -> dict[str, Any]:
    entries = _load_entries(pdf_path)
    if not entries:
        return {
            "found": False,
            "full_problem_statement": "",
            "official_solution_text": "",
            "source_page_start": None,
            "source_page_end": None,
            "source_fragments": [],
        }

    hint = str(statement_hint or "").strip()
    candidate_entries = entries
    if task_number is not None:
        task_matches = [
            entry
            for entry in candidate_entries
            if int(entry.get("task_number") or -1) == int(task_number)
        ]
        task_matches = [
            entry for entry in task_matches if _statement_strength(str(entry.get("statement") or "")) >= 30
        ]
        if task_matches:
            candidate_entries = task_matches

    if variant_number is not None:
        variant_matches = [
            entry
            for entry in candidate_entries
            if entry.get("variant") is not None and int(entry.get("variant")) == int(variant_number)
        ]
        variant_matches = [
            entry for entry in variant_matches if _statement_strength(str(entry.get("statement") or "")) >= 30
        ]
        if variant_matches:
            candidate_entries = variant_matches

    best_score = -1.0
    best_entry: dict[str, Any] | None = None

    for idx, entry in enumerate(candidate_entries):
        score = 0.0
        statement_strength = _statement_strength(str(entry.get("statement") or ""))
        if statement_strength < 16:
            score -= 2.5
        elif statement_strength < 30:
            score -= 1.2
        elif statement_strength < 60:
            score -= 0.35
        if task_number is not None:
            if int(entry.get("task_number") or -1) == int(task_number):
                score += 2.0
            else:
                score -= 0.2

        if variant_number is not None:
            entry_variant = entry.get("variant")
            if entry_variant is None:
                score -= 0.05
            elif int(entry_variant) == int(variant_number):
                score += 1.5
            else:
                score -= 1.0

        if hint:
            score += _similarity(hint, str(entry.get("statement") or ""))

        # Stable tiebreaker by original order.
        stable_index = int(entry.get("index") or (idx + 1))
        score -= stable_index * 0.0001
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry is None:
        best_entry = candidate_entries[0] if candidate_entries else entries[0]

    return {
        "found": True,
        "task_number": best_entry.get("task_number"),
        "variant": best_entry.get("variant"),
        "full_problem_statement": str(best_entry.get("statement") or "").strip(),
        "official_solution_text": str(best_entry.get("official_solution") or "").strip(),
        "source_page_start": int(best_entry.get("page_start") or 0) or None,
        "source_page_end": int(best_entry.get("page_end") or 0) or None,
        "source_fragments": best_entry.get("source_fragments") or [],
    }
