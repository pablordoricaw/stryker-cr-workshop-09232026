# resources/

Databricks Asset Bundle (DAB) resource definitions — the maintainer packaging
and reproducibility mechanism (versioned infra + app definition), and the basis
of the optional Finance "package your work as a DAB" stretch.

The DAB is **not** the required participant provisioning path: participants
provision through a plain setup notebook in the Workspace UI. The bundle exists
so the provided infrastructure and app are versioned and re-runnable.

> Placeholder. The DAB skeleton (`databricks.yml` + the resource YAMLs that live
> here) is added by ticket #3 (Provisioning — DAB skeleton + participant setup
> notebook). Kept minimal until then.
