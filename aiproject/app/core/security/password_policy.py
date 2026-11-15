import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints

from app.core.exceptions import BusinessError
from app.shared.types.phone import MOBILE_PATTERN

_CHARACTER_GROUPS = tuple(re.compile(pattern) for pattern in (r"[A-Z]", r"[a-z]", r"[0-9]", r"[^A-Za-z0-9]"))


def _validate_characters(password: str) -> str:
    if not re.fullmatch(r"[!-~]+", password):
        raise ValueError("密码只能使用英文字母、数字和常见英文符号")
    if sum(group.search(password) is not None for group in _CHARACTER_GROUPS) < 2:
        raise ValueError("密码至少包含大写字母、小写字母、数字、符号中的两类")
    return password


UserChosenPassword = Annotated[
    str, StringConstraints(min_length=8, max_length=128), AfterValidator(_validate_characters)
]


def reject_account_password(password: str, username: str, contact: str | None = None) -> None:
    phone = (contact or "").strip()
    if password.casefold() == username.casefold() or (re.fullmatch(MOBILE_PATTERN, phone) and password == phone):
        raise BusinessError(422, "新密码不能与登录账号或手机号相同")
