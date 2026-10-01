from datetime import datetime

import pytest
from pydantic import ValidationError

from src.exceptions import NotFound
from src.schemas import CustomModel, UTCDateTime, datetime_to_utc_str
from src.utils import generate_random_alphanum


def test_not_found_has_a_resource_detail() -> None:
    exception = NotFound()

    assert (exception.status_code, exception.detail) == (404, "Resource not found")


def test_datetime_serialization_is_utc_and_honors_dump_options() -> None:
    class Example(CustomModel):
        created_at: UTCDateTime
        history: list[UTCDateTime]
        indexed: dict[str, UTCDateTime]
        value: int

    model = Example(
        created_at=datetime.fromisoformat("2026-01-02T03:04:05.123456+08:00"),
        history=[datetime.fromisoformat("2026-01-02T03:04:05+08:00")],
        indexed={"updated": datetime.fromisoformat("2026-01-02T03:04:05.12-05:00")},
        value=1,
    )

    assert datetime_to_utc_str(model.created_at) == "2026-01-01T19:04:05.123456Z"
    assert model.model_dump(mode="json", exclude={"value"}) == {
        "created_at": "2026-01-01T19:04:05.123456Z",
        "history": ["2026-01-01T19:04:05Z"],
        "indexed": {"updated": "2026-01-02T08:04:05.120000Z"},
    }
    schema = Example.model_json_schema(mode="serialization")
    assert schema["properties"]["created_at"]["format"] == "date-time"

    with pytest.raises(ValueError, match="timezone-aware"):
        datetime_to_utc_str(datetime(2026, 1, 2, 3, 4, 5))

    with pytest.raises(ValidationError, match="timezone"):
        Example(
            created_at=datetime(2026, 1, 2, 3, 4, 5),
            history=[],
            indexed={},
            value=1,
        )


def test_custom_model_does_not_implicitly_normalize_datetime() -> None:
    class Example(CustomModel):
        created_at: datetime

    model = Example(created_at=datetime.fromisoformat("2026-01-02T03:04:05+08:00"))

    assert model.model_dump(mode="json") == {"created_at": "2026-01-02T03:04:05+08:00"}


def test_random_alphanum_validates_length() -> None:
    value = generate_random_alphanum(32)

    assert len(value) == 32
    assert value.isalnum()

    with pytest.raises(ValueError, match="positive"):
        generate_random_alphanum(0)
