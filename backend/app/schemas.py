import re
import json
import base64
from io import BytesIO
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Optional, Any
from app.utils.safe_http import validate_pdf_url


class UserRegister(BaseModel):
    username: str = Field(max_length=32)
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    full_name: str = Field(max_length=100)
    school: str = Field(max_length=100)
    grade: int

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        v = v.strip()
        if len(v) < 3 or len(v) > 32:
            raise ValueError("Имя пользователя: от 3 до 32 символов")
        if not re.match(r"^[a-zA-Z0-9_\-а-яА-ЯёЁ]+$", v):
            raise ValueError("Имя пользователя содержит недопустимые символы")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8 or len(v.encode("utf-8")) > 72:
            raise ValueError("Пароль: не менее 8 символов и не более 72 байт")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        v = v.strip().lower()
        if len(v) > 254 or "@" not in v:
            raise ValueError("Некорректный email")
        return v

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, v):
        if v < 1 or v > 11:
            raise ValueError("Класс: от 1 до 11")
        return v

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v):
        if len(v.strip()) > 100:
            raise ValueError("Имя слишком длинное")
        return v.strip()


class UserLogin(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=100)
    school: Optional[str] = Field(default=None, max_length=100)
    grade: Optional[int] = None
    bio: Optional[str] = Field(default=None, max_length=500)
    phone: Optional[str] = Field(default=None, max_length=20)
    telegram: Optional[str] = Field(default=None, max_length=100)
    vk: Optional[str] = Field(default=None, max_length=100)
    github: Optional[str] = Field(default=None, max_length=100)
    avatar_url: Optional[str] = Field(default=None, max_length=500_000)

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, v):
        if v is not None and (v < 1 or v > 11):
            raise ValueError("Класс: от 1 до 11")
        return v

    @field_validator("bio")
    @classmethod
    def validate_bio(cls, v):
        if v is not None and len(v) > 500:
            raise ValueError("Биография: не более 500 символов")
        return v

    @field_validator("avatar_url")
    @classmethod
    def validate_avatar_url(cls, v):
        if v is None or not v:
            return v
        if v.startswith("data:"):
            if not re.fullmatch(
                r"data:image/(?:png|jpeg|webp|gif);base64,[A-Za-z0-9+/]+={0,2}",
                v,
                re.IGNORECASE,
            ):
                raise ValueError("Аватар должен быть PNG, JPEG, WebP или GIF в Base64")
            try:
                encoded = v.split(",", 1)[1]
                image_bytes = base64.b64decode(encoded, validate=True)
                if not image_bytes or len(image_bytes) > 350 * 1024:
                    raise ValueError("Размер изображения превышает 350 КБ")
                from PIL import Image
                with Image.open(BytesIO(image_bytes)) as image:
                    if image.format not in {"PNG", "JPEG", "WEBP", "GIF"}:
                        raise ValueError("Формат изображения не поддерживается")
                    width, height = image.size
                    if width < 1 or height < 1 or width > 2048 or height > 2048 or width * height > 4_000_000:
                        raise ValueError("Размеры изображения превышают лимит")
                    if getattr(image, "n_frames", 1) > 1:
                        raise ValueError("Анимированные изображения не поддерживаются")
                    image.verify()
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError("Файл аватара повреждён или имеет неверный формат") from exc
            return v
        parsed = urlsplit(v)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError("Аватар должен быть HTTPS URL или допустимым изображением")
        return v


class TaskCreate(BaseModel):
    title: str = Field(max_length=200)
    problem_statement: str = Field(max_length=50_000)
    answer: str = Field(max_length=500)
    subject: str = Field(max_length=50)
    grade: Optional[int] = None
    difficulty: Optional[str] = Field(default="easy", max_length=20)
    points: Optional[int] = 10
    input_format: Optional[str] = Field(default=None, max_length=2_000)
    output_format: Optional[str] = Field(default=None, max_length=2_000)
    examples: Optional[str] = Field(default=None, max_length=20_000)
    solution_explanation: Optional[str] = Field(default=None, max_length=50_000)
    topic: Optional[str] = Field(default=None, max_length=100)
    tags: Optional[str] = Field(default=None, max_length=2_000)
    attachments: Optional[Any] = None
    source_pdf_url: Optional[str] = Field(default=None, max_length=2_048)
    source_solution_pdf_url: Optional[str] = Field(default=None, max_length=2_048)
    source_page_start: Optional[int] = None
    source_page_end: Optional[int] = None
    source_fragments: Optional[Any] = None
    full_problem_statement: Optional[str] = Field(default=None, max_length=50_000)
    official_solution_text: Optional[str] = Field(default=None, max_length=50_000)
    free_ai_explanation: Optional[str] = Field(default=None, max_length=50_000)
    free_ai_status: Optional[str] = Field(default=None, max_length=32)

    @field_validator("source_pdf_url", "source_solution_pdf_url")
    @classmethod
    def validate_source_pdf_url(cls, v):
        if v is None or not v.strip():
            return v
        try:
            return validate_pdf_url(v, resolve=False)
        except ValueError as exc:
            raise ValueError("PDF должен быть HTTPS-ссылкой с разрешённого источника") from exc

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, v):
        if v is not None and (v < 1 or v > 11):
            raise ValueError("Класс: от 1 до 11")
        return v

    @field_validator("points")
    @classmethod
    def validate_points(cls, v):
        if v is not None and (v < 1 or v > 100):
            raise ValueError("Баллы: от 1 до 100")
        return v

    @field_validator("attachments", "source_fragments")
    @classmethod
    def validate_json_payload(cls, v):
        if v is None:
            return v
        try:
            encoded = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError):
            raise ValueError("Некорректный JSON-параметр")
        if len(encoded) > 1_000_000:
            raise ValueError("Размер вложений или фрагментов превышает лимит")
        if isinstance(v, list) and len(v) > 100:
            raise ValueError("Слишком много элементов во вложениях или фрагментах")
        return v
