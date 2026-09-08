---
title: Researchers
status: draft
confidence: low
type: concept
sources: []
---

# Researchers

Research team and key collaborator directory. Populate by ingesting lab member profiles and collaboration agreements.

Each researcher record captures:

- **Identity** — name, title/role (PI / postdoc / PhD student / research scientist / collaborator), institution, email, ORCID
- **Research focus** — primary research area, active projects, methodological expertise
- **Contributions to this lab's work** — papers co-authored (link to [[papers]]), datasets collected, protocols developed
- **Responsibilities** — what this person leads or contributes to; mentees
- **Status** — current / former / external collaborator; expected duration for students/postdocs

**How to populate:**

1. Ingest lab member profiles or CV pages:
   ```
   synthadoc ingest "https://<institution>/faculty/<pi>" -w <wiki>
   ```

Cross-link to [[papers]], [[methodology]], and [[findings]].
