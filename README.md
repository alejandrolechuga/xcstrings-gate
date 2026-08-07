# xcstrings-gate

A translation-coverage gate for Xcode String Catalogs (`.xcstrings`) that
runs in CI, works offline, and gets plurals right.

## Why this exists

Xcode auto-extracts every `LocalizedStringKey` into your `.xcstrings`
catalog, but a string being *in* the catalog only makes it *translatable* —
not *translated*. Nothing in the toolchain stops a new PR from shipping an
English-only entry: no build error, no warning, no CI check. The catalog
silently grows a debt tail. `xcstrings-gate` closes that gap.

The alternatives (Crowdin, Lokalise, Phrase, etc.) all require pushing
your strings to a hosted TMS. If you want a coverage floor without moving
strings out of the repo, there hasn't been an option — until now.

## The two things worth leading with

### 1. Baseline ratchet — adopt on a codebase already in debt

You almost certainly already have untranslated strings. A gate that fails
on all of them from day one is a gate you turn off. `xcstrings-gate` reads
a `baseline.json` file listing every `(key, language)` pair that's currently
grandfathered. The gate blocks **only new** untranslated pairs. As debt gets
paid down, re-running `--write-baseline` shrinks the file. The baseline may
only shrink — a growing baseline means a new English-only string slipped
in, which is exactly what the tool exists to prevent.

The baseline is per-language, keyed by string:

```json
{
  "required_langs": ["es", "pt-BR"],
  "keys": {
    "some.old.key": ["pt-BR"],
    "half.done.key": ["es"]
  }
}
```

Adding a third required language does **not** force a wholesale re-baseline
of every key already missing only that one language.

### 2. Plurals are correct

Naive coverage tools check `entry.localizations[lang]` and stop. That
passes a half-translated plural: if `es.variations.plural.one` is
`translated` but `es.variations.plural.other` is still `new`, most tools
call it done. Xcode ships the untranslated case as English at runtime.

`xcstrings-gate` requires *every* sub-case (plural category, device
variant) of a variations entry to be translated **and non-empty**. A
half-translated plural fails the gate.

Same rule for device variations (`iphone` / `ipad` / `mac` / ...): all
declared cases must be translated.

## The one sanctioned exception: `shouldTranslate: false`

Some strings genuinely should not be localized — symbols, format-only
fragments (`"%@"`), brand names, unit abbreviations (`"kcal"`), emoji.
Xcode has native support: select the string → **"Don't Translate"**, which
sets `"shouldTranslate": false` in the catalog JSON.

That flag is the **only** sanctioned way to opt a string out of the gate.
Reasons:

1. **Co-located with the string** — a reader sees *why* it ships without a
   translation right there in the PR diff.
2. **Xcode-native** — survives Xcode edits, no bespoke exclusion file.
3. **Reviewable** — a separate exclusion list drifts and rots.

The gate also skips keys with `extractionState == "stale"` (Xcode's marker
for "key no longer referenced in code"), because those are dead weight,
not shipping strings.

## Install

Runtime dependency: **none**. Python 3.9+ stdlib only.

```bash
# Copy the two Python files (xcstrings_gate.py, xcstrings_io.py) into
# your repo, e.g. tools/xcstrings-gate/, then invoke directly.
```

Or as a package:

```bash
pip install xcstrings-gate
```

## Use

Single catalog:

```bash
python3 xcstrings_gate.py \
    --catalog 'path/to/YourApp/Localizable.xcstrings' \
    --baseline .github/xcstrings-baseline.json \
    --langs es,pt-BR
```

Multiple catalogs (per-target modules, `InfoPlist.xcstrings`, etc.) —
repeat `--catalog`, or use a glob:

```bash
python3 xcstrings_gate.py \
    --catalog 'ios/**/Localizable.xcstrings' \
    --catalog 'ios/**/InfoPlist.xcstrings' \
    --baseline .github/xcstrings-baseline.json \
    --langs es,pt-BR,fr
```

Bootstrap the baseline from your current state (once, on adoption):

```bash
python3 xcstrings_gate.py \
    --catalog '...' --baseline '...' --langs es,pt-BR \
    --write-baseline
```

### GitHub Actions

```yaml
name: xcstrings-gate
on: pull_request

jobs:
  xcstrings-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Enforce translation coverage
        # No setup-python needed — ubuntu-latest ships one.
        run: |
          python3 tools/xcstrings-gate/xcstrings_gate.py \
            --catalog 'path/to/YourApp/Localizable.xcstrings' \
            --baseline .github/xcstrings-baseline.json \
            --langs es,pt-BR
```

An `action.yml` wrapper (`uses: alejandrolechuga/xcstrings-gate@v1`) is
planned — see [issues](https://github.com/alejandrolechuga/xcstrings-gate/issues).

## Flags

| Flag | Purpose |
| --- | --- |
| `--catalog GLOB` | Path or glob to an `.xcstrings` file. **Repeat** to gate multiple catalogs; violations aggregate. |
| `--baseline PATH` | Baseline JSON file. Missing file is treated as an empty baseline. |
| `--langs es,pt-BR` | Comma-separated list of required language codes. |
| `--strict-states` | Only `translated` counts as translated. **Default:** `translated` **and** `needs_review` both count (matches Xcode's "shows in-app" behaviour). |
| `--remediation-hint TEXT` | Extra line printed on failure — plug in a project-specific pointer. |
| `--list` | Print every current `(key, missing_langs)` pair and exit 0. |
| `--write-baseline` | Snapshot the current violation set as the baseline. **Do not use this to silence a new violation.** |

Exit codes: `0` clean · `1` new violation(s) beyond the baseline · `2`
usage/IO error.

## State semantics

| State | Counts as translated? |
| --- | --- |
| `translated` | Yes |
| `needs_review` | Yes by default; **no** under `--strict-states` |
| `new` | Never (this is Xcode's placeholder-not-yet-translated state) |
| Empty `value` | Never, regardless of state |
| Language entry absent | Never |

Default `needs_review == translated` matches what Xcode itself does — a
`needs_review` string renders in-app instead of falling back to English —
so blocking on it by default would fail on completely functional apps.

## `xcstrings_io.py` — the byte-for-byte serializer

Bundled as a standalone module. Xcode's JSON dialect is very specific
(2-space indent, `"k" : v` with spaces around the colon, empty objects as
`{\n\n<indent>}`, no trailing newline). A vanilla `json.dump` reformats all
8k lines and destroys the PR diff. Use this instead:

```python
import json
from xcstrings_io import dumps

with open(path, encoding="utf-8") as f:
    obj = json.load(f)
# ...mutate obj...
with open(path, "w", encoding="utf-8") as f:
    f.write(dumps(obj))
```

Self-check on any catalog:

```bash
python3 xcstrings_io.py path/to/Localizable.xcstrings
# → round-trip OK (byte-for-byte identical)
```

### Ordering caveat

Preserves **insertion order**, not Xcode's locale-aware key collation.
Round-tripping existing files is byte-for-byte identical (their order is
already baked in). Appending locales to existing entries produces a
minimal diff. **Creating a brand-new entry** will land wherever the dict
put it, which may not be where Xcode would sort it — Xcode will silently
re-sort on next save. If greenfield writes are common in your workflow,
open the catalog in Xcode and save once after your tool run.

## Development

```bash
git clone https://github.com/alejandrolechuga/xcstrings-gate
cd xcstrings-gate
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[test]'
pytest
```

CI runs the suite on Python 3.9–3.13 and self-checks the serializer against
the bundled fixture.

## Non-goals

- Any network I/O — this tool never talks to a TMS.
- Language detection / auto-translation.
- Enforcing translation *quality* — `needs_review` still counts by default
  because Xcode ships it in-app. Use `--strict-states` if you'd rather block
  on it.

## License

MIT. See [LICENSE](LICENSE).
