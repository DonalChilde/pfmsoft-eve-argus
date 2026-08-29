"""Common type definitions for ESI Argus.

Most of these types are useful for documentation purposes only, as they are just aliases
for built-in types. However, they can help improve code readability and provide context
about the expected values.
"""

from enum import StrEnum
from typing import Literal

TypeID = int
RegionID = int

Language = Literal["en", "de", "fr", "ja", "ru", "zh", "es", "ko"]


class LanguageEnum(StrEnum):
    EN = "en"
    DE = "de"
    FR = "fr"
    JA = "ja"
    RU = "ru"
    ZH = "zh"
    ES = "es"
    KO = "ko"
