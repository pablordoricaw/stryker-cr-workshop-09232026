"""Black-box reproducibility coverage for the committed ITSM generator."""

from __future__ import annotations

import csv
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "generators" / "itsm" / "generate.py"
DATA = ROOT / "data" / "itsm"


def test_itsm_generator_is_byte_reproducible_and_commits_complete_seed() -> None:
    """The generator's own two-output comparison protects all binary artifacts."""
    completed = subprocess.run(
        [shutil.which("uv") or "uv", "run", "--script", GENERATOR, "--check-reproducible"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert len(list((DATA / "documents").rglob("*.pdf"))) == 25
    with (DATA / "transactional" / "lakebase" / "service_tickets.csv").open() as seed:
        tickets = list(csv.DictReader(seed))
    assert len(tickets) == 3_000
    assert [ticket["incident_id"] for ticket in tickets[:5]] == [
        f"INC-{202600000 + offset:07d}" for offset in range(5)
    ]
    assert (DATA / "transactional" / "delta" / "service_tickets" / "_delta_log" / "00000000000000000000.json").is_file()
    assert (DATA / "transactional" / "lakebase" / "cmdb_configuration_items.csv").is_file()
