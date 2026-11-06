"""Every workflow builds and tests against the same pinned nitro-common commit.

A checkout of nitro-wagering/common without a pinned ref follows common's main, so an unrelated
deploy picks up whatever merged there last. Each workflow pins `env.COMMON_REF` to a full SHA;
bump it deliberately, in every workflow at once.
"""

import re
from pathlib import Path

import yaml

ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".github" / "workflows").is_dir())
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))


def _common_checkouts(doc):
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            with_ = step.get("with") or {}
            if (
                str(step.get("uses", "")).startswith("actions/checkout")
                and with_.get("repository") == "nitro-wagering/common"
            ):
                yield with_


def test_every_common_checkout_uses_the_pinned_ref():
    pins = {}
    for path in WORKFLOWS:
        doc = yaml.safe_load(path.read_text())
        checkouts = list(_common_checkouts(doc))
        if not checkouts:
            continue
        for with_ in checkouts:
            assert with_.get("ref") == "${{ env.COMMON_REF }}", (
                f"{path.name}: common checkout must use env.COMMON_REF"
            )
        sha = str((doc.get("env") or {}).get("COMMON_REF", ""))
        assert re.fullmatch(r"[0-9a-f]{40}", sha), (
            f"{path.name}: env.COMMON_REF must be a full commit SHA"
        )
        pins[path.name] = sha
    assert pins, "no workflow checks out nitro-common"
    assert len(set(pins.values())) == 1, f"workflows pin different nitro-common commits: {pins}"
