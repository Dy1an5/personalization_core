from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from personalization_core.api.app import create_app
from personalization_core.api.auth import TokenAuthenticator
from personalization_core.sdk.async_client import PersonalizationEngine


BASELINE = Path(__file__).parents[2] / "docs" / "openapi-0.1.0.json"


def _operations(spec: dict[str, object]) -> dict[str, set[str]]:
    paths = cast(dict[str, object], spec["paths"])
    operations: dict[str, set[str]] = {}
    for path, value in paths.items():
        if isinstance(value, dict):
            methods = cast(dict[str, object], value)
            operations[path] = {
                method
                for method in methods
                if method in {"get", "post", "put", "patch", "delete"}
            }
    return operations


def _current_openapi() -> dict[str, object]:
    engine = PersonalizationEngine.from_sqlite(":memory:")
    app = create_app(
        engine=engine,
        authenticator=TokenAuthenticator({"release-test": "release-tenant"}),
        initialize_engine=False,
    )
    return app.openapi()


def test_openapi_release_baseline_has_no_breaking_operation_removals() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    current = _current_openapi()
    expected = _operations(baseline)
    actual = _operations(current)

    info = cast(dict[str, object], current["info"])
    assert info["version"] == "0.1.0"
    for path, methods in expected.items():
        assert path in actual, f"removed OpenAPI path: {path}"
        assert methods <= actual[path], f"removed OpenAPI operation: {path} {methods - actual[path]}"
