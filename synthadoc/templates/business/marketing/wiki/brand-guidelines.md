---
title: Brand Guidelines
status: draft
confidence: low
type: concept
sources: []
---

# Brand Guidelines

Brand identity standards and usage rules. Populate by ingesting your brand guidelines document or style guide.

Each brand guideline record captures:

- **Brand identity** — brand name, tagline, brand purpose statement (why the brand exists), brand personality descriptors (3–5 adjectives)
- **Logo** — primary logo, logo variations (light/dark, monochrome), minimum size, clear space requirements, prohibited uses (don't stretch, don't rotate, don't change colors)
- **Color palette** — primary colors (hex, RGB, CMYK, Pantone), secondary colors, usage proportions, accessibility contrast ratios (WCAG AA minimum)
- **Typography** — primary typeface (headings), secondary typeface (body), fallback web-safe fonts, type scale, bold/italic usage rules
- **Imagery and photography** — approved image style (lifestyle / editorial / abstract), prohibited imagery, image sourcing guidelines (stock sites, in-house)
- **Voice and tone** — brand voice characteristics, tone variations by channel (formal for legal, conversational for social), vocabulary and phrases to avoid
- **Do/don't examples** — side-by-side examples of correct and incorrect brand application

**How to populate:**

1. Ingest your brand guidelines PDF:
   ```
   synthadoc ingest docs/brand/brand-guidelines.pdf -w <wiki>
   ```

Cross-link to [[messaging]], [[content-strategy]], and [[campaigns]].
