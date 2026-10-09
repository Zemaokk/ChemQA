# ChemQA documentation

Start with the path that matches your task. These documents describe the current implementation; dated experiment records describe the configuration used for that experiment.

| Need | Start here |
| --- | --- |
| Learn the workflow from installation to an inspectable answer | [Your first literature question](tutorials/first-question.md) |
| Build, configure, recover, or verify an installation | [How-to guides](how-to/README.md) |
| Look up flags, settings, file contracts, or metrics | [Reference](reference/README.md) |
| Understand the pipeline and its limits | [Explanation](explanation/README.md) |
| Understand a consequential design choice | [Architecture decision records](decisions/README.md) |
| See notable changes | [Changelog](../CHANGELOG.md) |
| Update these documents | [Documentation maintenance](how-to/maintain-documentation.md) |

The documentation follows [Diátaxis](https://diataxis.fr/): tutorials teach through a guided exercise, how-to guides solve a specific task, reference describes interfaces, and explanation develops the reasoning. Decisions and release history have their own indexes.

Machine-readable experiment records remain at their original `docs/*.json` paths because validation scripts and frozen manifests consume them. The [record catalog](reference/experiment-records.md) gives them context. Frozen `evaluation/**/RUBRIC.md` files are protocol inputs, not current user guides.

Previous prose and the authored PDF report are preserved locally under `legacy-docs/2026-10-09/`. That archive is ignored by Git and excluded from source snapshots. Current documentation does not require it. See the [migration map](reference/documentation-migration.md) for replacements.
