# Design language

Revision requested by the owner to follow the reference UI at
`https://team9.bdctraining.cloud/` (the same product, built by another team).
`blueprint.json` is unchanged: this is a visual revision, not a requirement change.

## What was adopted from the reference

| Element | Reference | Here |
|---|---|---|
| Palette | rose `#b8486f` with a rose→pink→violet gradient | same tokens in `static/app.css` |
| Background | warm pink paper with soft radial glows | `radial-gradient` layers on `--paper` |
| Header | gradient heart-pulse tile, wordmark and tagline, controls on the right | same, plus our sign-in/session controls and settings gear |
| Navigation | pill controls | our nav links are pills; the current page is highlighted |
| Cards | white, 18–22 px radius, soft shadow, hairline border | `.card`, `.medicine-hero`, `.section-card` |
| Call to action | full-width gradient "Imbas Kod Ubat" panel with a camera tile | `.scan-panel` |
| Manual entry | divider text "kalau tak boleh imbas, taip kod ubat", mono input, rose search button | `.divider`, `.search-row` |
| Headline numbers | plain row: 39 ubat · 14 kategori · 16 perlu preskripsi | `.stats` (ubat, kategori, belum disahkan, imbasan) |
| How it works | three numbered cards | `.steps` / `.step` |
| Medicine page | photo card, category eyebrow, title, chips, action buttons, one card per section | `.medicine-layout`, `.chips`, `.section-card` |
| Section labels | small uppercase eyebrows (KEGUNAAN, DOS, AMARAN …) | `.eyebrow` |

Not copied: the reference's "Pengguna / Doktor" toggle. Our roles are enforced on
the server from `docs/AUTH.md`, so a client-side toggle would pretend to change
permissions. The role is shown as a badge instead.

## Tokens (`:root` in `static/app.css`)

```
--rose #b8486f   --rose-dark #9c3359   --rose-2 #d4668d   --violet #a98bd6
--ink #2b1a23    --ink-soft #6f5561    --paper #fdf5f8     --card #fffdfe
--line #f2dbe6   --teal #0d9488        --amber #b45309    --danger #b42318
--radius 22px    --radius-sm 14px      --gradient 135deg rose → pink → violet
```

Type: the system UI stack (Segoe UI first) as in the reference. No web fonts, so
there is no third-party request and the CSP stays strict.

## Rules

- Colour carries meaning: teal for verified/success, amber for unverified and
  prescription flags, red for refusals and errors. Never a colour alone — every
  status also has text.
- All styling lives in `/static/app.css`; templates carry no inline `style`
  attributes (the CSP ignores them).
- Every page keeps: one `h1`, the support channel in the footer, the privacy and
  terms links, and the contact line required before launch.
- Printable label pages keep their own `@media print` rules.

## Screens touched

Home (signed in and landing), sign-in, scan, search, medicine details, history,
favourites, import, labels, team, usage, settings, billing, privacy, terms and the
error pages all use the new tokens. The functional hooks (`data-error`,
`data-scan`, `data-image`, `data-page`, form ids) are unchanged, so the acceptance
tests and the browser checks still pass.
