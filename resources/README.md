# resources/

Databricks Asset Bundle (DAB) resource definitions — the maintainer packaging
and reproducibility mechanism (versioned infra + app definition), and the basis
of the optional Finance "package your work as a DAB" stretch.

The DAB is **not** the required participant provisioning path: participants
provision through a plain setup notebook in the Workspace UI
(`notebooks/00_setup`). The bundle exists so the provided infrastructure and app
are versioned and re-runnable.

## Bring-your-own-catalog

Participants (and this bundle) do **not** create catalogs — each team already
has its own. The `catalog` variable in `../databricks.yml` names an **existing**
catalog to target; the bundle defines only the **schema** and **UC Volume**
inside it, plus the **app**.

## Layout

| File                   | Resource                                             |
| ---------------------- | ---------------------------------------------------- |
| `../databricks.yml`    | Bundle name, variables, and targets                  |
| `workshop.schema.yml`  | The workshop schema, in the (existing) catalog       |
| `workshop.volume.yml`  | The UC Volume where source documents land            |
| `workshop.app.yml`     | The provided data app (code added by a later ticket) |

Validate with:

```bash
databricks bundle validate --profile <your-profile>
```

Override the target catalog per environment, e.g.
`databricks bundle validate --var catalog=my_existing_catalog --profile <p>`.
