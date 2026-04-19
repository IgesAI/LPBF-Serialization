"""Immutable identifier value objects.

These types are the *only* way a build code or part serial enters the
system. Construction validates the input and never coerces or fills in
missing fields - malformed inputs raise ``ValueError``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

_PREFIX_PATTERN: Final = re.compile(r"^[A-Z][A-Z0-9#_-]{0,7}$")


@dataclass(frozen=True, slots=True)
class BuildCode:
    """A build-plate token, e.g. ``B#0001``.

    The string representation is always ``<prefix><zero-padded number>``.
    """

    prefix: str
    number: int
    digits: int

    def __post_init__(self) -> None:
        if not _PREFIX_PATTERN.match(self.prefix):
            raise ValueError(f"Invalid build-code prefix: {self.prefix!r}")
        if self.number < 1:
            raise ValueError(f"Build number must be >= 1, got {self.number}")
        if self.digits < 1 or self.digits > 12:
            raise ValueError(f"digits must be in [1, 12], got {self.digits}")
        if len(str(self.number)) > self.digits:
            raise ValueError(
                f"Build number {self.number} exceeds {self.digits}-digit capacity"
            )

    def __str__(self) -> str:
        return f"{self.prefix}{self.number:0{self.digits}d}"

    @classmethod
    def parse(cls, value: str, *, prefix: str, digits: int) -> BuildCode:
        if not value.startswith(prefix):
            raise ValueError(
                f"Build code {value!r} does not start with expected prefix {prefix!r}"
            )
        tail = value[len(prefix) :]
        if len(tail) != digits:
            raise ValueError(
                f"Build code {value!r} tail length {len(tail)} != expected {digits}"
            )
        if not tail.isdigit():
            raise ValueError(f"Build code tail {tail!r} is not numeric")
        return cls(prefix=prefix, number=int(tail), digits=digits)

    def next(self) -> BuildCode:
        return BuildCode(prefix=self.prefix, number=self.number + 1, digits=self.digits)


@dataclass(frozen=True, slots=True)
class PartSerial:
    """A per-part serial of the form ``<BuildCode>-<index>`` (1-based)."""

    build_code: BuildCode
    index: int

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError(f"Part index must be >= 1, got {self.index}")

    def __str__(self) -> str:
        return f"{self.build_code}-{self.index}"

    @classmethod
    def parse(cls, value: str, *, prefix: str, digits: int) -> PartSerial:
        if "-" not in value:
            raise ValueError(f"Part serial {value!r} missing '-' separator")
        head, _, tail = value.rpartition("-")
        if not tail.isdigit():
            raise ValueError(f"Part serial tail {tail!r} is not numeric")
        return cls(
            build_code=BuildCode.parse(head, prefix=prefix, digits=digits),
            index=int(tail),
        )
