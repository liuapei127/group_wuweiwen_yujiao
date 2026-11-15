from typing import Annotated

from pydantic import StringConstraints

MOBILE_PATTERN = r"^1[3-9][0-9]{9}$"
MobileNumber = Annotated[str, StringConstraints(strip_whitespace=True, pattern=MOBILE_PATTERN)]
