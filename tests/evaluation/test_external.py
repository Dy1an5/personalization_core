import os

import pytest


@pytest.mark.external
def test_external_provider_evaluation_is_explicitly_opt_in() -> None:
    if os.environ.get("EVAL_EXTERNAL") != "1":
        pytest.skip("external provider evaluations are opt-in")
    # The real provider adapter is supplied by a deployment-specific test package.
    assert os.environ["EVAL_EXTERNAL"] == "1"
