# Product previews: source

Every image in this folder is a screenshot of GrantBridge itself, not a stock image or a mock-up. The
organization (Harbor Lantern Tutoring Collective), the account (dana@harborlantern.example), the award terms, and
every number in them are samples, invented for the demonstration.

| File | What it shows | Size |
| --- | --- | --- |
| `workspace-preview.webp` | Should We Pursue? → Can we afford to win? for the sample grant New England Youth Opportunity Fund | 1600 × 1296 |
| `site-find.webp` | Find Grants: sample listings with their fit checks, on the **How It Works** page | 1500 × 1154 |
| `site-pursue.webp` | A completed pursuit assessment, on the **How It Works** page | 1500 × 1218 |
| `site-portfolio.webp` | The recommended portfolio, on the **How It Works** page | 1500 × 1218 |

- Captured 2026-10-23 from a local server in practice mode (no AI calls) with a throwaway database.
- Reproduce them with `python -m scripts.capture_preview` and `python -m scripts.capture_site_previews`
  (instructions at the top of each script).
- WebP, captured at 3× device scale and resized down, so text stays sharp on a high-resolution screen.

As GrantBridge's own screens, they have no third-party license terms. The hero photograph's license is recorded
in `../photos/ATTRIBUTION.md`.
