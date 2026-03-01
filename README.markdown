# bibgetter

[![tests](https://github.com/bibgetter/bibgetter/actions/workflows/tests.yml/badge.svg)](https://github.com/bibgetter/bibgetter/actions/workflows/tests.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

`bibgetter` is a command-line tool for mathematicians writing papers in LaTeX,
making bibliography management easier.
You can also read this documentation online
at [`bibgetter.github.io`](https://bibgetter.github.io).

## Quick navigation

- [**Installation**](#installation)
- [**Operations**](#operations): [`add`](#bibgetter-add), [`get`](#bibgetter-get), [`sync`](#bibgetter-sync), [`pull`](#bibgetter-pull), [`alias`](#bibgetter-alias), [`bibitems`](#bibgetter-bibitems)
- [**Workflow & identifier types**](#workflow)
- [**Biber formatting**](#biber-formatting)

## Installation

It is best to install it using `pipx`, which is a clean way to install Python
applications.

As an end user, the best solution is likely to run

```bash
pipx install --preinstall "bibtexparser>=2.0.0b8" git+https://github.com/bibgetter/bibgetter
```

As a developer (so this is a reminder to myself, mostly), it is

```bash
pipx install --editable --force .
```

### Note on the `bibtexparser` version

The `--preinstall "bibtexparser>=2.0.0b8"` option is a workaround to force the
use of `bibtexparser v2.x`.  As of early 2026 only pre-release (`2.0.0b9`)
versions of bibtexparser v2 are on PyPI;  `pip install bibtexparser` without
`--pre` installs the incompatible v1.4.x series.

## Workflow

There is a central BibLaTeX file at `~/.bibgetter/bibliography.bib`
that acts as a single repository for all bibliography entries.  Once an entry
is in the central file it can be copied to any local project without a further
network request.

## Supported identifier types

| Source | Raw ID | URL form |
|--------|--------|----------|
| **arXiv** | `2411.14814`, `arXiv:math/0309136` | `https://arxiv.org/abs/2411.14814` |
| **MathSciNet** | `MR4865600` | `https://mathscinet.ams.org/mathscinet/relay-station?mr=4865600` |
| **DOI** | `10.4007/annals.2013.178.1.3` | `https://doi.org/10.4007/annals.2013.178.1.3` |

URLs are accepted everywhere a raw ID is accepted; `bibgetter` extracts the
canonical ID automatically.

## Operations

### `bibgetter add` — add entries to the central file

```
bibgetter add <id-or-url> [<id-or-url> ...]
bibgetter add --file article.aux [chapter1.aux ...]
```

Fetches BibLaTeX records and appends them to the central bibliography.
Already-present entries are silently skipped (no redundant network requests).

**From `.aux` files:** `--file` accepts one or more paths (including shell
globs, e.g. `--file latex.out/*.aux`).  All of the following citation commands
found in the file are recognised:

| Command | Source |
|---------|--------|
| `\citation{key}` | standard BibTeX, natbib, apacite, … |
| `\abx@aux@cite{0}{key}` | biblatex (current, with refsection argument) |
| `\abx@aux@cite{key}` | biblatex (older format) |
| `\@input{child.aux}` | nested aux files from `\include{}` (parsed recursively) |

### `bibgetter get` — print entries to stdout

```
bibgetter get <id-or-url> [<id-or-url> ...]
```

Prints BibLaTeX records to stdout.
If an entry is not yet in the central file it is fetched automatically first.

### `bibgetter sync` — copy entries to a local bibliography file

```
bibgetter sync --file article.aux --local bibliography.bib
bibgetter sync <key> [<key> ...] --local bibliography.bib
```

Copies entries from the central file to a local `bibliography.bib`, adding only
those that are not already present.

> **Guaranteed offline** once the central file is populated.

### `bibgetter pull` — add and sync in one step

```
bibgetter pull --file article.aux --local bibliography.bib
```

Equivalent to `add` followed by `sync`.  Typical build workflow:

```bash
bibgetter pull --file article.aux --local bibliography.bib
pdflatex article
biber article
pdflatex article
```

### `bibgetter alias` — manage key aliases

```
bibgetter alias <alias> <target-id-or-url>
bibgetter alias
```

Adds a human-readable alias stored in the BibLaTeX `ids` field, which biber
recognises as an alternative key.

```bash
bibgetter alias rouquier-dimension MR2183393
bibgetter get rouquier-dimension   # prints entry renamed to the alias
bibgetter alias                    # lists all defined aliases
```

### `bibgetter bibitems` — convert to `\bibitem` list

```
bibgetter bibitems [file.bib]
```

Converts a `.bib` file to a list of `\bibitem` commands suitable for pasting
into a journal submission that does not accept BibLaTeX.  Uses the
[biblatex2bibitem](https://gitlab.com/Nickkolok/biblatex2bibitem) LaTeX
package.

```bash
bibgetter bibitems                     # convert central bibliography
bibgetter bibitems local.bib           # convert a specific file
```

> **Requires:** `pdflatex`, `biber`, `pdftotext` (poppler-utils), and the
> `biblatex2bibitem` LaTeX package (on CTAN / TeX Live).

## Biber formatting

After every write to the central bibliography `bibgetter` runs `biber --tool`
to normalise the file.  This:

* sorts entries alphabetically by key;
* normalises ISBN formatting;
* standardises author initials;
* encodes non-ASCII characters as ASCII-safe equivalents;
* aligns field values for readability;
* validates the data model and reports unexpected fields.

The configuration is stored in `~/.bibgetter/biber-formatting.conf` (copied
from the package on first run).  Notable behaviour:

| Behaviour | How |
|-----------|-----|
| Field names are **lowercased** | `<output_fieldcase>lower</output_fieldcase>` in conf |
| **`year`** is preserved (not renamed to `date`) | `--output-legacy-dates` CLI flag |
| **`journal`** is preserved (not renamed to `journaltitle`) | `<sourcemap>` in conf |

You can edit the conf file to customise biber's behaviour.  The flags
`--output-safechars`, `--fixinits`, `--isbn-normalise`, and
`--output-legacy-dates` are passed by `bibgetter` on the command line and
cannot be overridden via the configuration file.

## The central bibliography file

The central file lives at `~/.bibgetter/bibliography.bib` by default.
Use `--data-directory <path>` to override this for testing or multiple
projects:

```bash
bibgetter add 2307.15338 --data-directory /path/to/project/.bibgetter
```

### MathSciNet record keys

MathSciNet keys are zero-padded to 7 digits (e.g. `MR0012345` rather than
`MR12345`).  The short form is preserved in the `ids` field so that citations
using either form resolve correctly.

### DOIs with special characters

Some DOIs contain characters (e.g. parentheses) that are invalid in BibTeX
record keys.  `bibgetter` strips those from the key while preserving the
original DOI in the `doi` field.

