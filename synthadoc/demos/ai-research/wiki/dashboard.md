---
title: Dashboard
tags: [dashboard]
status: active
confidence: high
created: 2026-05-09
sources: []
orphan: false
aliases: []
---

# AI Research Tracker — Dashboard

## Contradicted Pages

```dataview
TABLE dateformat(created, "MMM dd, yyyy") AS "Created", status, confidence
FROM "wiki"
WHERE status = "contradicted"
SORT created DESC
```

## Orphan Pages

```dataview
TABLE dateformat(created, "MMM dd, yyyy") AS "Created", status
FROM "wiki"
WHERE orphan = true
SORT created DESC
```

## Recently Added

```dataview
TABLE dateformat(created, "MMM dd, yyyy") AS "Added", status, confidence
FROM "wiki"
WHERE file.name != "index" AND file.name != "dashboard" AND file.name != "purpose"
SORT created DESC
LIMIT 10
```

---

## Recently Updated

```dataview
TABLE dateformat(date(updated), "MMM dd, yyyy") AS "Updated", status, confidence
FROM "wiki"
WHERE updated
  AND file.name != "index" AND file.name != "dashboard" AND file.name != "purpose"
SORT date(updated) DESC
LIMIT 10
```

*Pages that have been re-ingested with new source material since their initial creation.*

---

## Recently Archived

```dataview
TABLE dateformat(file.mtime, "MMM dd, yyyy") AS "Archived", confidence
FROM "wiki"
WHERE status = "archived"
SORT file.mtime DESC
LIMIT 10
```

*Pages retired from active use. To restore a page, change `status` back to `active`.*
