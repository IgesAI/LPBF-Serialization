"""Tests for BuildCode and PartSerial value objects."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from lpbf_serializer.domain.ids import BuildCode, PartSerial


class TestBuildCode:
    def test_formats_with_zero_padding(self) -> None:
        c = BuildCode(prefix="B#", number=7, digits=4)
        assert str(c) == "B#0007"

    def test_next_increments(self) -> None:
        c = BuildCode(prefix="B#", number=9, digits=4)
        assert str(c.next()) == "B#0010"

    def test_rejects_zero_or_negative_number(self) -> None:
        with pytest.raises(ValueError, match="Build number must be >= 1"):
            BuildCode(prefix="B#", number=0, digits=4)

    def test_rejects_overflow(self) -> None:
        with pytest.raises(ValueError, match="exceeds"):
            BuildCode(prefix="B#", number=10_000, digits=4)

    def test_rejects_bad_prefix(self) -> None:
        with pytest.raises(ValueError, match="Invalid build-code prefix"):
            BuildCode(prefix="bad prefix", number=1, digits=4)

    def test_parse_roundtrip(self) -> None:
        c = BuildCode(prefix="B#", number=123, digits=4)
        assert BuildCode.parse(str(c), prefix="B#", digits=4) == c

    def test_parse_rejects_wrong_digits(self) -> None:
        with pytest.raises(ValueError, match="tail length"):
            BuildCode.parse("B#012", prefix="B#", digits=4)

    @given(n=st.integers(min_value=1, max_value=9_999))
    def test_parse_is_inverse_of_str(self, n: int) -> None:
        c = BuildCode(prefix="B#", number=n, digits=4)
        assert BuildCode.parse(str(c), prefix="B#", digits=4) == c


class TestPartSerial:
    def test_formats(self) -> None:
        bc = BuildCode(prefix="B#", number=1, digits=4)
        assert str(PartSerial(build_code=bc, index=3)) == "B#0001-3"

    def test_rejects_zero_index(self) -> None:
        bc = BuildCode(prefix="B#", number=1, digits=4)
        with pytest.raises(ValueError, match="Part index must be >= 1"):
            PartSerial(build_code=bc, index=0)

    def test_parse_roundtrip(self) -> None:
        bc = BuildCode(prefix="B#", number=42, digits=4)
        s = PartSerial(build_code=bc, index=7)
        assert PartSerial.parse(str(s), prefix="B#", digits=4) == s
