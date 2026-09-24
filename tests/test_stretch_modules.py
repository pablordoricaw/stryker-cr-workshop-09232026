"""Repo invariants for the optional Tier-3 stretch modules (#16).

These are structural, dependency-free checks (no Spark, no SDK, no YAML lib) that
lock in the three deliverables so they cannot silently rot:

1. **From-scratch mode** adds an identical, markdown-only, default-off marker cell on
   every graded *build* stage (and deliberately not on ``00_setup``).
2. **Package as a DAB** ships a *set* of two independently-deployable example bundles
   (not one monolith) that package the built work (pipeline + app) and target the
   schema/volume ``00_setup`` provisioned, rather than re-declaring them.
3. **Add your own** provides a starter + gated solution that reuse the existing
   checkpoint override knobs rather than changing the framework.

The bundles' *semantic* validity is covered by ``databricks bundle validate
--strict`` (run out-of-band); these tests assert the workshop-specific invariants
that validate does not, namely CREATE-CATALOG-free, no managed schema/volume resource
(so a deploy never collides with ``00_setup``'s objects), bundle-local app source,
no dev-mode name prefixing, and the documented cross-references.
"""

from __future__ import annotations

import os

import workshop

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(workshop.__file__)))

# The graded build stages that carry the from-scratch marker. 00_setup is
# excluded on purpose: it provisions the environment rather than teaching a build.
BUILD_STAGES = (
    "01_bronze_docs.py",
    "01_bronze_txn.py",
    "02_silver_docs.py",
    "03_gold.py",
    "04_metadata.py",
    "05_metric_views.py",
    "06_genie.py",
    "07_app.py",
)

MARKER_HEADING = "# MAGIC ## 🚀 From-scratch mode (optional stretch)"
# A stable slice of the marker body that must be byte-identical across every
# stage (this is the "documented once, applied consistently" guarantee).
MARKER_INVARIANT = (
    "# MAGIC to the **`workshop.check(...)` cell at the end**, which is identical in both\n"
    "# MAGIC modes and is the only thing that grades you."
)

# The canonical bootstrap loop every notebook's first code cell must contain, so
# `import workshop` resolves from any depth inside a Databricks Git folder.
BOOTSTRAP_LINE = 'while not os.path.isfile(os.path.join(_root, "workshop", "__init__.py")):'


def _read(*parts: str) -> str:
    with open(os.path.join(REPO_ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _yaml_body(text: str) -> str:
    """Drop full-line ``#`` comments so token checks see effective YAML, not the
    explanatory prose (which intentionally names the anti-patterns it avoids)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


# --- Deliverable 3: from-scratch mode -------------------------------------------


def test_from_scratch_marker_on_every_build_stage():
    for stage in BUILD_STAGES:
        text = _read("notebooks", stage)
        assert text.count(MARKER_HEADING) == 1, f"{stage} must carry exactly one marker"
        assert MARKER_INVARIANT in text, f"{stage} marker body drifted"


def test_from_scratch_marker_body_identical_across_stages():
    bodies = {stage: _read("notebooks", stage) for stage in BUILD_STAGES}
    # The heading + invariant body slice must appear verbatim in each stage.
    for stage, text in bodies.items():
        assert MARKER_HEADING in text and MARKER_INVARIANT in text, stage


def test_setup_stage_has_no_from_scratch_marker():
    # 00_setup provisions; it is not a build stage, so it stays out of scope.
    assert MARKER_HEADING not in _read("notebooks", "00_setup.py")


def test_from_scratch_marker_is_markdown_only():
    # Every line the marker cell adds is a `# MAGIC` markdown line, with no widget and no
    # code, so it cannot change what the checkpoint asserts.
    for stage in BUILD_STAGES:
        text = _read("notebooks", stage)
        start = text.index(MARKER_HEADING)
        cell = text[start : text.index("# COMMAND", start)]
        for line in cell.splitlines():
            if line.strip():
                assert line.startswith("# MAGIC"), f"{stage}: non-markdown line in marker: {line!r}"


def test_from_scratch_marker_links_to_the_doc():
    for stage in BUILD_STAGES:
        assert "docs/stretch/README.md" in _read("notebooks", stage)


# --- Deliverable 1: package as a DAB (bundle SET, not a monolith) ---------------

BUNDLE_ROOT = ("solutions", "finance", "stretch", "package_as_dab_bundle")
BUNDLES = ("pipeline", "app")


def test_bundle_set_has_two_independent_bundles_and_no_foundation():
    # Two separate databricks.yml files == two independently-deployable bundles
    # (the anti-monolith guarantee).
    for name in BUNDLES:
        path = os.path.join(REPO_ROOT, *BUNDLE_ROOT, name, "databricks.yml")
        assert os.path.isfile(path), f"missing bundle: {name}/databricks.yml"
    # The old 'foundation' bundle is gone: schema/volume are provisioned by
    # 00_setup, not packaged, so nothing double-creates them.
    foundation = os.path.join(REPO_ROOT, *BUNDLE_ROOT, "foundation")
    assert not os.path.exists(foundation), "foundation bundle must not exist (00_setup provisions schema/volume)"


def _bundle_yaml_bodies(name: str):
    bundle_dir = os.path.join(REPO_ROOT, *BUNDLE_ROOT, name)
    for dirpath, _dirs, files in os.walk(bundle_dir):
        for fname in files:
            if fname.endswith((".yml", ".yaml")):
                yield f"{name}/{fname}", _yaml_body(_read(os.path.join(dirpath, fname)))


def test_bundles_are_create_catalog_free():
    for name in BUNDLES:
        for label, body in _bundle_yaml_bodies(name):
            assert "catalogs:" not in body, f"{label} defines a catalog resource"
            assert "CREATE CATALOG" not in body.upper(), f"{label} creates a catalog"


def test_bundles_declare_no_managed_schema_or_volume_resource():
    # 00_setup provisions the schema + volume; the bundles TARGET them by
    # variable. Declaring them as managed resources would make a first deploy
    # collide with the pre-existing UC objects. Guard both `resources:` keys.
    for name in BUNDLES:
        for label, body in _bundle_yaml_bodies(name):
            assert "schemas:" not in body, f"{label} must not manage a schema resource"
            assert "volumes:" not in body, f"{label} must not manage a volume resource"


def test_bundles_use_deterministic_names_not_dev_mode():
    # mode: development prefixes names with characters illegal in UC identifiers
    # and would drift from what the notebooks/checkpoints expect.
    for name in BUNDLES:
        body = _yaml_body(_read(*BUNDLE_ROOT, name, "databricks.yml"))
        assert "mode: development" not in body, f"{name} must not use dev-mode name prefixing"


def test_pipeline_targets_catalog_schema_by_variable():
    text = _read(*BUNDLE_ROOT, "pipeline", "databricks.yml")
    assert "variables:" in text
    assert "catalog:" in text and "schema:" in text


def test_pipeline_references_notebooks_by_workspace_path():
    job = _yaml_body(_read(*BUNDLE_ROOT, "pipeline", "resources", "medallion.job.yml"))
    assert "${var.notebooks_root}" in job, "pipeline job must reference notebooks by workspace path"
    # Serverless-first: no classic cluster pinned on the tasks.
    assert "new_cluster" not in job and "job_cluster_key" not in job


def test_app_bundle_is_namespace_aware():
    text = _read(*BUNDLE_ROOT, "app", "databricks.yml")
    assert "app_name:" in text


def test_app_source_is_bundle_local_not_a_workspace_path():
    # The app bundle must ship its OWN source (bundle deploy uploads it), not
    # depend on a pre-existing /Workspace/ checkout.
    db = _yaml_body(_read(*BUNDLE_ROOT, "app", "databricks.yml"))
    resource = _yaml_body(_read(*BUNDLE_ROOT, "app", "resources", "data_app.app.yml"))
    # sync.paths scopes the sync root so deploy ships the local app source.
    assert "sync:" in db and "paths:" in db, "app bundle must declare sync.paths for bundle-local source"
    # No source_code_path anywhere may point at an ambient Workspace location.
    combined = db + "\n" + resource
    assert "/Workspace/" not in combined, "app source must be local, not a /Workspace/ path"


def test_bundle_set_readme_documents_the_why():
    readme = _read(*BUNDLE_ROOT, "README.md").lower()
    for token in ("independently-deployable", "monolith", "blast radius", "runbook"):
        assert token in readme, f"bundle-set README missing the '{token}' rationale"


# --- Deliverable 2: add your own (reuses existing knobs) ------------------------


def test_add_your_own_solution_uses_existing_checkpoint_knobs():
    text = _read("solutions", "finance", "stretch", "add_your_own.py")
    assert "metric_views=" in text, "must validate the new view via the 05_metrics knob"
    assert "expected_sources=" in text and "benchmark_questions=" in text


# --- Shared: the stretch surfaces exist and bootstrap correctly -----------------


def test_stretch_notebooks_and_solutions_exist_and_bootstrap():
    surfaces = (
        ("notebooks", "stretch", "package_as_dab.py"),
        ("notebooks", "stretch", "add_your_own.py"),
        ("solutions", "finance", "stretch", "package_as_dab.py"),
        ("solutions", "finance", "stretch", "add_your_own.py"),
    )
    for parts in surfaces:
        text = _read(*parts)
        assert BOOTSTRAP_LINE in text, f"{'/'.join(parts)} missing the bootstrap loop"


def test_stretch_doc_hub_covers_all_three_modules():
    doc = _read("docs", "stretch", "README.md").lower()
    assert "package your work as a dab" in doc
    assert "add your own" in doc
    assert "from-scratch" in doc
