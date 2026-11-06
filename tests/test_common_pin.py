"""Every workflow builds and tests against the same pinned nitro-common commit.

A deploy that checks out common at a different commit from the one CI tested ships code CI never
ran, and a checkout with no ref tests against whatever common main is that day. Each workflow that
checks out nitro-wagering/common takes its ref from ``env.COMMON_REF`` and pins that to a full SHA;
bump it deliberately, in every workflow at once.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator

WORKFLOWS = sorted((Path(__file__).resolve().parents[1] / ".github" / "workflows").glob("*.y*ml"))
ALLOWED_REFS = {"${{ env.COMMON_REF }}", "${{ inputs.common_ref || env.COMMON_REF }}"}


def _common_checkouts(doc: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            with_ = step.get("with") or {}
            if (
                str(step.get("uses", "")).startswith("actions/checkout")
                and with_.get("repository") == "nitro-wagering/common"
            ):
                yield with_


def test_every_common_checkout_uses_the_one_pinned_sha() -> None:
    pins: dict[str, str] = {}
    for path in WORKFLOWS:
        doc = yaml.safe_load(path.read_text())
        checkouts = list(_common_checkouts(doc))
        if not checkouts:
            continue
        for with_ in checkouts:
            assert with_.get("ref") in ALLOWED_REFS, (
                f"{path.name}: common checkout must take its ref from env.COMMON_REF, "
                f"got {with_.get('ref')!r}"
            )
        sha = str((doc.get("env") or {}).get("COMMON_REF", ""))
        assert re.fullmatch(r"[0-9a-f]{40}", sha), (
            f"{path.name}: env.COMMON_REF must be a full commit SHA"
        )
        pins[path.name] = sha
    assert pins, "no workflow checks out nitro-common"
    assert len(set(pins.values())) == 1, f"workflows pin different nitro-common commits: {pins}"


def test_the_guard_sees_both_workflows_that_check_out_common() -> None:
    seen = {
        path.name for path in WORKFLOWS if list(_common_checkouts(yaml.safe_load(path.read_text())))
    }

    assert seen == {"test.yml", "build-and-deploy.yml"}
