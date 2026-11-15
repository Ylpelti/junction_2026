# English synthetic dataset en-v2

`patients.en-v2.json` is the active, explicitly synthetic dataset. It preserves
all 41 observation values/statuses/timestamps and all 21 encounter dates across
four patients from `patients.json` (archived Finnish v1). Source wording is English;
“does not currently smoke” does **not** mean “never smoked”. The original v1 file
and any persisted v1 evidence remain unchanged.

Every patient, encounter and observation has a new UUIDv5 in the namespace
`https://cancersignal.invalid/demo/en-v2/{kind}/{key}`. The complete correspondence
is `en-v2-id-map.json`. New patient names end in `EN v2`. The active frontend selects only the four canonical English patient IDs;
archived API records remain readable.
No general language detection, automatic translation or source rewriting occurs.

From `backend/`, after applying existing Alembic migrations:

```sh
.venv/bin/python -m app.db.demo validate
.venv/bin/python -m app.db.demo seed
.venv/bin/python -m app.db.demo list
```

Seed is now insert-only: a changed existing fixture causes a transactional error,
not an evidence rewrite. Create a new dataset version and new IDs when source
content changes. The explicitly guarded reset applies only to active en-v2
identities; never use it to migrate old evidence. No reset is required for migration.

Laine covers persistent symptoms and declining Hb; Nieminen covers a colonoscopy
plan with unknown completion; Heikkinen covers completed colonoscopy, subsequent
resolution and current explicit negatives; Korhonen covers routine care and
explicit negatives. Clinical predictors remain missing where undocumented.
The independent English extraction fixture additionally covers conflicting
investigation documentation and active unintentional weight loss.

New IDs isolate observation/embedding caches. Extraction prompt version
`clinical-extraction-en-3` and explanation prompt version `en-explanation-plan-2`
separate inference caches from v1. Reindex new patients if using dense retrieval.
No live model calls are enabled by seeding. The default structured-only extractor
does not interpret arbitrary narrative notes.

The original [v1 guide](README.md) is historical documentation, including old IDs,
commands and the former update-on-seed behavior; use this guide for active demos.
