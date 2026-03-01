import argparse
import arxiv
import bibtexparser
from dataclasses import dataclass
import fake_useragent
import json
import glob
import os
import re
import rich
import rich.columns
import requests
import shutil
import subprocess
import sys
import tempfile
import time

# ---------------------------------------------------------------------------
# Configuration dataclass (replaces module-level globals)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BibgetterConfig:
    """
    Immutable configuration object holding all file-system paths used by
    bibgetter.

    Using a frozen dataclass eliminates the module-level mutable globals that
    previously required ``global`` statements in ``main()`` and made direct
    testing of helper functions impossible (see design.md).

    Usage::

        config = BibgetterConfig()                       # default ~/.bibgetter
        config = BibgetterConfig.from_directory(tmpdir)  # custom location
    """

    directory: str = os.path.expanduser("~/.bibgetter")

    @property
    def bibliography(self) -> str:
        """Full path to the central bibliography file."""
        return os.path.join(self.directory, "bibliography.bib")

    @property
    def configuration(self) -> str:
        """Full path to the biber formatting configuration file."""
        return os.path.join(self.directory, "biber-formatting.conf")

    @classmethod
    def from_directory(cls, directory: str) -> "BibgetterConfig":
        """Create a config rooted at an arbitrary directory (used for testing)."""
        return cls(directory=directory)


def is_arxiv_id(id: str) -> bool:
    """
    Check if the given string is a valid arXiv identifier.

    An arXiv identifier follows the pattern: `YYYY.NNNN` or `YYYY.NNNNN`,
    optionally followed by 'v' and a version number.

    To match old identifiers, whose patterns is an absolute mess, prefix with `arXiv:`

    https://info.arxiv.org/help/arxiv_identifier.html
    https://info.arxiv.org/help/arxiv_identifier_for_services.html
    """
    old = r"^arXiv:.*$"
    new = r"^\d{4}\.\d{4,5}(v\d+)?$"

    return bool(re.fullmatch(old, id) or re.fullmatch(new, id))


def guess_arxiv_id(id: str) -> str | dict[str, str] | None:
    """
    Guess the arXiv ID from the given identifier.
    Accepts both raw arXiv IDs and URLs in various formats.
    """
    if is_arxiv_id(id):
        return id
    url_pattern = r"^(?:https?://)?arxiv\.org/(?:abs|html|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?$"
    match = re.match(url_pattern, id)
    if match:
        arxiv_id = match.group(1)
        if is_arxiv_id(arxiv_id):
            return arxiv_id
    return None


def is_mathscinet_id(id: str) -> bool:
    """
    Check if the given identifier is a valid MathSciNet ID.

    A valid MathSciNet ID starts with `MR` followed by 1 to 7 digits.
    Alternatively, it starts starts with `mr:`, and then a valid MR identifier.
    TODO: move the flexibility to the guess_mathscinet_id function, and make this
    function accept only the canonical form (MR, then exactly seven digits).
    """
    pattern = r"^(MR|mr:MR)\d{1,7}$"

    return re.fullmatch(pattern, id) is not None


def guess_mathscinet_id(id: str) -> str | dict[str, str] | None:
    """
    Guess the MathSciNet ID from the given identifier.
    Accepts both raw MathSciNet IDs and URLs in various formats.
    """
    if is_mathscinet_id(id):
        return id
    url_pattern = (
        r"^(?:https?://)?mathscinet\.ams\.org/mathscinet/relay-station\?mr=(\d{1,7})$"
    )
    match = re.match(url_pattern, id)
    if match:
        mr_id = f"MR{match.group(1)}"
        if is_mathscinet_id(mr_id):
            return mr_id
    return None


def is_doi(id: str) -> bool:
    """
    Check if the given string is a valid DOI identifier.

    DOIs start with '10.' followed by 4-9 digits (the registrant code),
    a forward slash, and a non-empty suffix of non-whitespace characters.

    See https://www.doi.org/doi_handbook/2_Numbering.html for the DOI syntax.
    """
    pattern = r"^10\.\d{4,9}(/\S+)+$"
    return re.fullmatch(pattern, id) is not None


def guess_doi(id: str) -> str | dict[str, str] | None:
    """
    Guess the DOI from the given identifier.

    The original design principle of bibgetter was to use the canonical ID as the primary
    record identifier for a bibliography item. This does not work for DOIs since they could
    include parentheses and other symbols which are not allowed in record identifiers. Thus
    for some DOIs this function returns a dictionary with 'actual_id' and 'bibtex_id' keys
    instead of just a single string.

    There seems to be no standard description of what a valid record identifier could be since
    biber/bibtex/bibtool/etc each have their own non-identical parsers, see
    https://tex.stackexchange.com/a/582026 .
    """
    # Extract DOI from URL if needed
    id = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/(.+)$", r"\1", id.rstrip("/"))
    if is_doi(id):
        forbidden_symbols = "(){}#%\\=,\"'"
        cleaned_id = "".join([c for c in id if c not in forbidden_symbols])
        if cleaned_id != id:
            return {"actual_id": id, "bibtex_id": cleaned_id}
        else:
            return cleaned_id
    return None


def arxiv2biblatex(key, entry):
    """
    Convert an arXiv preprint to a BibLaTeX entry.

    One has to specify the key to be used: often the user will want to cite the current
    version of the preprint without actually specifying the version in the BibTeX key.
    """
    # the "true" id, including the version number
    id = entry.entry_id.split("/")[-1]
    authors = " and ".join([author.name for author in entry.authors])

    return (
        f"@online{{{key},\n"
        f"  author      = {{{authors}}},\n"
        f"  title       = {{{entry.title}}},\n"
        f"  year        = {{{entry.updated.year}}},\n"
        f"  eprinttype  = {{arxiv}},\n"
        f"  eprint      = {{{id}}},\n"
        f"  ids         = {{{id if key != id else ''}}},\n"
        f"  eprintclass = {{{entry.primary_category}}},\n"
        f"}}\n"
    )


def get_citations(content: str, base_dir: str | None = None) -> list:
    r"""
    Extract citation keys from the content of a ``.aux`` file.

    The following patterns are recognised:

    * ``\citation{key}`` -- standard BibTeX; also used by natbib, apacite,
      and other BibTeX-compatible packages.
    * ``\abx@aux@cite{0}{key}`` -- biblatex (current format, with refsection
      argument).
    * ``\abx@aux@cite{key}`` -- biblatex (older format, without refsection
      argument).
    * ``\@input{child.aux}`` -- when a LaTeX document uses ``\include``, the
      root ``.aux`` file delegates to per-chapter ``.aux`` files.  These are
      followed recursively when ``base_dir`` is provided.

    Args:
        content:  The raw text of a ``.aux`` file.
        base_dir: Directory containing the ``.aux`` file; used to resolve
            ``\@input`` references.  Pass ``None`` to disable recursive
            processing.

    Returns:
        A deduplicated list of citation keys.
    """
    patterns = [
        re.compile(r"\\citation\{([^}]+)\}"),
        re.compile(r"\\abx@aux@cite\{0\}\{([^}]+)\}"),
        re.compile(r"\\abx@aux@cite\{([^}0][^}]*)\}"),
    ]
    keys: set[str] = set()
    for pattern in patterns:
        keys.update(pattern.findall(content))

    # Recurse into child .aux files if the caller provided a base directory.
    if base_dir is not None:
        for child_name in re.findall(r"\\@input\{([^}]+)\}", content):
            child_path = os.path.join(base_dir, child_name)
            if os.path.isfile(child_path):
                try:
                    with open(child_path) as fh:
                        keys.update(
                            get_citations(
                                fh.read(), base_dir=os.path.dirname(child_path)
                            )
                        )
                except OSError:
                    pass

    return list(keys)


def make_argument_list(func):
    """
    Decorator to convert a single argument to a list if it is a string.

    This is useful for functions that expect a list of arguments, but the user only
    provides a single argument.
    """

    def enclose(argument):
        return func([argument]) if isinstance(argument, str) else func(argument)

    return enclose


@make_argument_list
def get_arxiv(ids):
    # if list of ids is empty, we don't do anything
    if not ids:
        return ""

    # get rid of arXiv: prefix if needed
    ids = [id.split(":")[-1] for id in ids]

    entries = []
    for id in ids:
        entry = arxiv.Client().results(arxiv.Search(id_list=list([id])))
        entries.append(arxiv2biblatex(id, next(entry)))

    return "\n".join(entries)


def clean_mathscinet_entry(entry):
    # other fields (like MRREVIEWER, or MRCLASS) will be removed by biber
    to_remove = ("ISSN",)
    if "DOI = {" in entry:
        to_remove = to_remove + ("URL",)

    lines = entry.strip().splitlines()
    lines = [line for line in lines if not line.lstrip().startswith(to_remove)]

    # if numerical part of key less than 7 characters, add long version as alternative
    key = lines[0].split("MR")[1][:-1]
    if len(key) < 7:
        long = f"{key.rjust(7, '0')}"
        lines = [lines[0].replace(key, long)] + [f"  IDS = {{MR{key}}},"] + lines[1:]

    return "\n".join(lines)


@make_argument_list
def get_mathscinet(ids):
    # if list of ids is empty, we don't do anything
    if not ids:
        return ""

    # drop the MR from the ids for the API
    ids = [id.lstrip("mr:").lstrip("MR") for id in ids]

    r = requests.get(
        "https://mathscinet.ams.org/mathscinet/api/publications/format",
        params={"formats": "bib", "ids": ",".join(ids)},
        headers={"User-Agent": fake_useragent.UserAgent().chrome},
    )

    # anything but 200 means something went wrong
    if not r.status_code == 200:
        print(f"URL was {r.url}")
        raise Exception("Received HTTP status code " + str(r.status_code))

    response = json.loads(r.text)
    entries = [clean_mathscinet_entry(entry["bib"]) for entry in response]

    return "\n".join(entries) + "\n"


def clean_doi_entry(entry, doi):
    """
    Clean a raw BibTeX entry returned by the CrossRef API.

    Performs the following transformations:
    * Rewrites the record key to the (sanitised) DOI.
    * Upgrades http links to https.
    * Removes the ``publisher`` field from ``@article`` entries because
      CrossRef often includes it while biber's default datamodel does not,
      producing validation warnings.
    """
    # Parse the entry to modify it
    bib = bibtexparser.parse_string(entry)
    entry = bib.entries[0]
    lines = entry.raw.strip().splitlines()
    # Always link to https
    for i, line in enumerate(lines):
        lines[i] = line.replace("http", "https")
    # Fix the key to be equal to the DOI, or rather to the sanitized version of DOI if necessary
    # (e.g., when DOI includes parentheses using it as a record key leads to biber parsing error)
    guessed_doi = guess_doi(doi)
    if isinstance(guessed_doi, dict) and "bibtex_id" in guessed_doi:
        doi = guessed_doi["bibtex_id"]
    lines[0] = lines[0].replace(entry.key, doi)
    # CrossRef includes a publisher field on @article entries, which biber's
    # default data model does not allow there (only on @book and related types).
    # Remove it to avoid --validate-datamodel warnings.
    if entry.entry_type.lower() == "article":
        lines = [
            line
            for line in lines
            if not re.match(r"^\s*publisher\s*=", line, re.IGNORECASE)
        ]

    return "\n".join(lines)


@make_argument_list
def get_doi(ids):
    """
    Fetch BibTeX entries for DOIs using the CrossRef API.
    """
    # if list of ids is empty, we don't do anything
    if not ids:
        return ""

    # Extract DOI from URLs if needed
    ids = [
        re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/(.+)$", r"\1", id.rstrip("/"))
        for id in ids
    ]

    entries = []
    for doi in ids:
        # TODO: figure out if crossref supports requesting multiple DOIs at once
        url = f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex"
        r = requests.get(url, headers={"User-Agent": fake_useragent.UserAgent().chrome})

        if r.status_code == 404:
            rich.print(f"[red]DOI {doi} not found")
            raise Exception(f"DOI {doi} not found")
        elif r.status_code != 200:
            rich.print(f"[red]Failed to fetch DOI {doi}: HTTP {r.status_code}")
            raise Exception(f"Failed to fetch DOI {doi}: HTTP {r.status_code}")

        entries.append(clean_doi_entry(r.text, doi))
        if len(ids) > 1:
            # sleep for 1 second to avoid rate limiting
            time.sleep(1)
    return "\n\n".join(entries) + "\n"


# triples of (predicate, action, guess) to resolve the keys
ACTIONS = {
    "arXiv": (is_arxiv_id, get_arxiv, guess_arxiv_id),
    "MathSciNet": (is_mathscinet_id, get_mathscinet, guess_mathscinet_id),
    "DOI": (is_doi, get_doi, guess_doi),
    # TODO implement zbMath
}


def canonical_id_candidates(id):
    """
    Return a list of possible canonical bibtex IDs for the given identifier.

    This is used to avoid listing multiple variations of the id in the central bibliography.
    For example, we don't want to add arXiv pdf URL and arXiv html URL as alternative ids to
    all arXiv entries, but we want to match them when looking up the entry.
    """
    ids = [id]
    for _, _, guess in ACTIONS.values():
        candidate = guess(id)
        if isinstance(candidate, dict) and "bibtex_id" in candidate:
            ids.append(candidate["bibtex_id"])
        elif candidate:
            ids.append(candidate)
    return ids


def alternative_ids(entry) -> list:
    # Field names may not be lowercase if the user edited the central file directly
    # (the biber formatter would normalise them, but manual edits bypass that).
    for key in entry.fields_dict:
        if key.lower() == "ids":
            return [id.strip() for id in entry[key].split(",")]
    return []


def bibliography_keys(bibliography) -> list:
    if not bibliography:
        return []

    defaults = [entry.key for entry in bibliography.entries]
    alternatives = [
        id for entry in bibliography.entries for id in alternative_ids(entry)
    ]

    return defaults + alternatives


def add_entries(keys, central, config: BibgetterConfig) -> int:
    """
    Add entries to the central bibliography.

    Returns the number of items written to the central bibliography.
    """
    # take keys, canonicalize them, remove the ones already in central file, and look up the missing ones
    # ignores local keys
    central_keys = set(bibliography_keys(central))
    missing = [
        key
        for key in keys
        if not any(id in central_keys for id in canonical_id_candidates(key))
    ]

    rich.print(
        f"{len(keys) - len(missing)} [default not bold]key(s)"
        f" already in central bibliography"
    )

    if not missing:
        return 0

    rich.print(
        f"Looking up {len(missing)} {'entry' if len(missing) == 1 else 'entries'}"
    )

    written = []

    for type in ACTIONS:
        predicate, action, guess = ACTIONS[type]
        # Select ids to process for the current action type,
        # transforming ID variants (hyperlinks, etc) into actual IDs using the
        # corresponding guess() function.
        # `matched` is a sublist of `missing` consisting of keys that we process, while
        # `ids_to_process` has canonicalized ID variants corresponding to keys in `matched`.
        matched = []
        ids_to_process = []
        for id in missing:
            if predicate(id):
                ids_to_process.append(id)
                matched.append(id)
            else:
                guessed_id = guess(id)
                # Sometimes guessed_id includes, separately, an ID to use in action() and a preferred
                # ID to use as a bibtex record identifier. Here we only need the former.
                if isinstance(guessed_id, dict) and "actual_id" in guessed_id:
                    guessed_id = guessed_id["actual_id"]
                if guessed_id:
                    ids_to_process.append(guessed_id)
                    matched.append(id)
        missing = sorted([id for id in missing if id not in matched])

        if len(matched) == 0:
            continue

        action_failed = False
        with open(config.bibliography, "a") as f:
            try:
                f.write(action(ids_to_process))
                written.extend(ids_to_process)
            except Exception as e:
                action_failed = True
                rich.print(f"[red]Error in retrieving {type} entries")
                rich.print(e)

        if not action_failed:
            rich.print(
                f"Added {len(matched)}"
                f" {'entry' if len(matched) == 1 else 'entries'} from {type}"
            )
            rich.print(
                rich.padding.Padding(
                    rich.columns.Columns(
                        [f"[green not bold]{key}" for key in matched],
                        equal=True,
                        expand=True,
                    ),
                    (0, 0, 0, 4),
                )
            )

    if missing:
        rich.print(f"Could not recognize {len(missing)} keys:")
        rich.print(
            rich.padding.Padding(
                rich.columns.Columns(
                    [f"[red not bold]{key}" for key in missing], equal=True, expand=True
                ),
                (0, 0, 0, 4),
            )
        )

    return len(written)


def sync_entries(keys, central, local, filename=None) -> int:
    """
    Synchronize entries from central to local

    Returns the number of newly added entries.
    """
    # take keys, remove the ones already in local file, and look up the missing ones
    # from the central bibliography file
    missing = [key for key in keys if key not in bibliography_keys(local)]

    rich.print(f"{len(missing)} [default not bold]key(s) not yet in local file")
    if len(missing) == 0:
        return 0

    entries = []

    for key in missing:
        if key not in bibliography_keys(central):
            rich.print(f"[red]Entry not found in central bibliography: [bold]{key}")
            continue

        entry = find_entry(key, central)
        if entry:
            entries.append(entry)
            continue

    # write to local bibliography (if set)
    if filename is not None:
        with open(filename, "a") as f:
            f.write("\n" + "\n\n".join(entry.raw for entry in entries))
            rich.print(
                f"[green]Wrote {len(entries)}"
                f" {'entry' if len(missing) == 1 else 'entries'} to local file"
            )

    return len(entries)


def write_configuration(config: BibgetterConfig):
    """
    Copy the bundled biber-formatting.conf to the config directory if it does
    not already exist.
    """
    if not os.path.exists(config.configuration):
        package_directory = os.path.dirname(__file__)
        default = os.path.join(package_directory, "biber-formatting.conf")

        os.makedirs(os.path.dirname(config.configuration), exist_ok=True)
        with open(default, "r") as src, open(config.configuration, "w") as target:
            target.write(src.read())


def format(filename, config: BibgetterConfig):
    """
    Format the bibliography file using biber.

    This is like running black on a Python file: an opinionated formatter.
    It will sort the entries, normalize ISBNs, ensure consistent field case,
    and so on.

    Flags used:

    * ``--output-legacy-dates``  keep ``year`` as-is instead of converting to
      biber's canonical ``date`` field.
    * ``--output-safechars``     use ASCII-safe character representations.
    * ``--fixinits``             normalise author initials.
    * ``--isbn-normalise``       normalise ISBN formatting.

    The biber-formatting.conf configuration additionally preserves ``journal``
    (rather than converting to ``journaltitle``) and sorts entries by key.
    """
    subprocess.call(
        [
            "biber",
            "--tool",
            "--output-safechars",
            "--fixinits",
            "--isbn-normalise",
            "--output_encoding=ascii",
            "--output-align",
            "--output-legacy-dates",
            f"--configfile={config.configuration}",
            "--validate-datamodel",
            f"--output_file={filename}",
            filename,
        ],
        stdout=subprocess.DEVNULL,
    )


def substitute_bibtex_key(entry_text, expected_key):
    """
    Substitute the record identifier of a bibtex entry.

    We use this to print a bibtex entry with the record identifier that was requested by the user,
    regardless of the record identifier used in the central bibliography.
    """
    lines = entry_text.splitlines()
    # Extract entry id from first line
    entry_id = re.search(r"{\s*([^,\s]+)", lines[0]).group(1)
    lines[0] = lines[0].replace("{" + entry_id, "{" + expected_key)
    # Replace expected_key with entry_id in ids field.
    # Match case-insensitively since the user may have edited the file manually.
    for i, line in enumerate(lines):
        if re.match(r"^\s*ids\s*=", line, re.IGNORECASE):
            lines[i] = re.sub(
                rf"([^\w]|^){re.escape(expected_key)}([^\w]|$)",
                rf"\g<1>{entry_id}\g<2>",
                line,
            )
    return "\n".join(lines)


def find_entry(key, central):
    """
    Return the entry matching the user-provided key, or None if not found.

    Handles aliases (entries whose ``ids`` field contains ``key``) as well as
    URL variants recognised by the ``guess_*`` functions in ACTIONS.

    Returns None in two situations:
     * ``central`` is None (no central bibliography file exists yet); callers
       should treat this the same as "entry not found".
     * The entry genuinely does not exist in the central bibliography.
    """
    if not central:
        return None
    found_entry = None
    key_variants = canonical_id_candidates(key)
    for entry in central.entries:
        if (entry.key in key_variants) or (key in alternative_ids(entry)):
            found_entry = entry
            break
    return found_entry


def get_entries(keys, central, config: BibgetterConfig):
    """
    Print entries from the central bibliography to stdout.

    If an entry is not found, attempt to add it first.

    Args:
        keys:    List of bibliography keys to show.
        central: The central bibliography database (may be ``None``).
        config:  Paths configuration object.
    """
    # First try to add any missing entries
    touched = add_entries(keys, central, config)
    if touched:
        format(config.bibliography, config)
        # Reload central bibliography with new entries
        central = bibtexparser.parse_file(config.bibliography)

    # Print entries
    for key in keys:
        entry = find_entry(key, central)
        if entry:
            print(substitute_bibtex_key(entry.raw, key))
        else:
            rich.print(f"[red]Unable to find or add entry: [bold]{key}")


def print_defined_aliases(central):
    """
    Print all aliases from the central bibliography.
    """
    if not central or not central.entries:
        rich.print("[yellow]No aliases defined")
        return
    alias_map = {}
    for entry in central.entries:
        ids = alternative_ids(entry)
        if ids:
            # An alternative id is considered an alias if the canonical key cannot be
            # guess()ed from it by any of the ACTIONS.
            aliases = [
                id
                for id in ids
                if id != entry.key
                and not any(guess(id) for _, _, guess in ACTIONS.values())
            ]
            for alias in aliases:
                alias_map[alias] = entry

    if not alias_map:
        rich.print("[yellow]No aliases defined")
        return

    # Sort by alias name and print
    for alias in sorted(alias_map.keys()):
        entry = alias_map[alias]
        authors = "(no author)"
        author_key = next((k for k in entry.fields_dict if k.lower() == "author"), None)
        if author_key:
            authors = (
                entry[author_key].split(" and ")[0].strip().split(",")[0]
            )  # Get first author
            if " and " in entry[author_key]:
                authors += " et al."
        title = "(no title)"
        title_key = next((k for k in entry.fields_dict if k.lower() == "title"), None)
        if title_key:
            title = entry[title_key].strip("{}")  # Remove braces from title
        rich.print(f"[green]{alias}[/green] \u2192 {entry.key} ({authors}: {title})")
    return


# ---------------------------------------------------------------------------
# bibitems conversion (uses the biblatex2bibitem LaTeX package)
# ---------------------------------------------------------------------------


def bibitems(bib_file: str | None, config: BibgetterConfig):
    r"""
    Convert a ``.bib`` file to a list of ``\bibitem`` commands and print them
    to stdout.

    Uses the `biblatex2bibitem <https://gitlab.com/Nickkolok/biblatex2bibitem>`_
    LaTeX package, which renders ``\bibitem`` source code as verbatim text in a
    PDF.  The text is then extracted via **pdftotext** (part of poppler-utils).

    Requires:

    * ``pdflatex`` (from any TeX distribution)
    * ``biber``
    * ``pdftotext`` (``brew install poppler`` / ``apt install poppler-utils``)
    * The ``biblatex2bibitem`` LaTeX package (on CTAN / TeX Live)

    Args:
        bib_file: Path to the ``.bib`` file to convert.  Pass ``None`` to use
                  the central bibliography.
        config:   Paths configuration object.
    """
    if bib_file is None:
        bib_file = config.bibliography

    if not os.path.isfile(bib_file):
        rich.print(f"[red]File not found: {bib_file}")
        return

    missing_tools = [
        t for t in ("pdflatex", "biber", "pdftotext") if shutil.which(t) is None
    ]
    if missing_tools:
        for tool in missing_tools:
            rich.print(f"[red]Required tool not found: [bold]{tool}")
        rich.print(
            "  pdflatex / biber : install a TeX distribution (e.g. TeX Live)\n"
            "  pdftotext        : brew install poppler  /  apt install poppler-utils"
        )
        return

    tex_source = (
        r"\documentclass{article}" + "\n"
        r"\usepackage[backend=biber]{biblatex}" + "\n"
        r"\addbibresource{refs.bib}" + "\n"
        r"\usepackage{biblatex2bibitem}" + "\n"
        r"\begin{document}" + "\n"
        r"\nocite{*}" + "\n"
        r"\printbibitembibliography" + "\n"
        r"\end{document}" + "\n"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        shutil.copy(bib_file, os.path.join(tmpdir, "refs.bib"))

        with open(os.path.join(tmpdir, "main.tex"), "w") as fh:
            fh.write(tex_source)

        for cmd in (
            ["pdflatex", "-interaction=nonstopmode", "main.tex"],
            ["biber", "main"],
            ["pdflatex", "-interaction=nonstopmode", "main.tex"],
        ):
            subprocess.call(
                cmd,
                cwd=tmpdir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        pdf_file = os.path.join(tmpdir, "main.pdf")
        if not os.path.isfile(pdf_file):
            rich.print(
                "[red]PDF generation failed.  Make sure the biblatex2bibitem"
                " LaTeX package is installed (CTAN: biblatex2bibitem)."
            )
            return

        result = subprocess.run(
            ["pdftotext", "-layout", pdf_file, "-"],
            capture_output=True,
            text=True,
            cwd=tmpdir,
        )
        text = result.stdout

        # biblatex2bibitem renders \bibitem commands as verbatim text in the
        # PDF.  Locate the first occurrence and print everything from there.
        start = text.find("\\bibitem")
        if start == -1:
            rich.print(
                "[yellow]No \\\\bibitem commands found in PDF output.\n"
                "Check that biblatex2bibitem rendered the bibliography."
            )
            return
        print(text[start:].rstrip())


def handle_aliases(central, operation_args, config: BibgetterConfig):
    """
    Handle the alias operation for managing bibliography key aliases by adding
    them to the ``ids`` field.
    """
    # If no arguments provided, print existing aliases from ids fields
    if len(operation_args) == 0:
        print_defined_aliases(central)
        return

    # Check if we have both alias and target
    if len(operation_args) != 2:
        rich.print("[red]Usage: bibgetter alias <alias> <target>")
        return

    alias = operation_args[0]
    target = operation_args[1]

    # First verify/add the target in central bibliography
    target_entry = None
    if central:
        target_entry = find_entry(target, central)

    if not target_entry:
        rich.print(
            f"[yellow]Target '{target}' not found in central bibliography. Attempting to add it..."
        )
        touched = add_entries([target], central, config)
        if touched:
            format(config.bibliography, config)
            rich.print(
                f"[green]Successfully added target '{target}' to central bibliography"
            )
            central = bibtexparser.parse_file(config.bibliography)
            target_entry = find_entry(target, central)
            if not target_entry:
                rich.print(
                    f"[red] Internal error: entry '{target}' successfully added, but not found afterwards!"
                )
                return
        else:
            rich.print(
                f"[red]Failed to add target '{target}'. Aborting alias creation."
            )
            return

    # Add alias to the ids field
    existing = alternative_ids(target_entry)
    if existing:
        if alias not in existing:
            existing.append(alias)
            target_entry["ids"] = ", ".join(existing)
    else:
        target_entry["ids"] = f"{alias}"

    # Write back the updated bibliography
    with open(config.bibliography, "w") as f:
        bibtexparser.write_file(f, central)
        format(config.bibliography, config)

    rich.print(f"[green]Added alias: {alias} \u2192 {target}")
    print(substitute_bibtex_key(target_entry.raw, alias))


def main(fake_args=None):
    parser = argparse.ArgumentParser(description="bibgetter")
    parser.add_argument(
        "operation",
        help="Operation to perform (add/sync/pull/get/alias/bibitems)",
        nargs="*",
    )
    parser.add_argument(
        "--file",
        help=".aux file(s); accepts multiple paths and shell globs",
        type=str,
        nargs="+",
    )
    parser.add_argument("--local", help="local bibliography file", type=str)
    parser.add_argument(
        "--data-directory", help="bibgetter directory location", type=str
    )
    args = parser.parse_args(fake_args)

    # Build the immutable config object (no global mutation).
    config = (
        BibgetterConfig.from_directory(args.data_directory)
        if args.data_directory
        else BibgetterConfig()
    )

    valid_operations = ["add", "sync", "pull", "get", "alias", "bibitems"]

    if not args.operation or args.operation[0] not in valid_operations:
        if not args.operation:
            rich.print("[red]No operation provided to bibgetter.")
        else:
            rich.print("[red]Invalid operation provided.")
        rich.print("Allowed operations:")
        rich.print("  [green]add[/green]      - Add entries to central bibliography")
        rich.print(
            "  [green]sync[/green]     - Sync entries from central to local bibliography"
        )
        rich.print(
            "  [green]pull[/green]     - Add entries to central and sync to local bibliography"
        )
        rich.print(
            "  [green]get[/green]      - Print entries from central bibliography"
        )
        rich.print("  [green]alias[/green]    - Manage bibliography key aliases")
        rich.print(
            "  [green]bibitems[/green] - Convert bibliography to \\bibitem commands"
        )
        return

    # On first run (and all subsequent runs) of bibgetter, write configuration.
    write_configuration(config)

    # Read the central bibliography file.
    central = None
    try:
        central = bibtexparser.parse_file(config.bibliography)
    except FileNotFoundError:
        pass

    if args.operation[0] == "alias":
        handle_aliases(central, args.operation[1:], config)
        return

    if args.operation[0] == "bibitems":
        bib_file = args.operation[1] if len(args.operation) > 1 else None
        bibitems(bib_file, config)
        return

    # Read the local bibliography file (if specified).
    local = None
    if args.local:
        try:
            local = bibtexparser.parse_file(args.local)
        except FileNotFoundError:
            pass

    # Collect keys: from command-line arguments and from .aux file(s).
    keys = []

    if args.file:
        for pattern in args.file:
            for filename in glob.glob(pattern):
                with open(filename) as fh:
                    keys.extend(
                        get_citations(fh.read(), base_dir=os.path.dirname(filename))
                    )

    if args.operation[0] not in ["add", "sync", "pull", "get", "format"]:
        raise ValueError(
            "Invalid operation. Only operations are: add, sync, pull, get, format."
        )

    # Add the keys from the command-line arguments.
    keys.extend(args.operation[1:])
    keys = list(set(keys))

    rich.print(f"Considering {len(keys)} [default not bold]key(s)")

    target = None
    if hasattr(args, "local"):
        target = args.local

    if args.operation[0] == "get":
        # TODO: support local bibliography file here
        get_entries(keys, central, config)
        return

    if args.operation[0] == "add":
        touched = add_entries(keys, central, config)
        if touched > 0:
            format(config.bibliography, config)

    if args.operation[0] == "sync":
        sync_entries(keys, central, local, filename=target)

    if args.operation[0] == "pull":
        touched = add_entries(keys, central, config)
        if touched > 0:
            format(config.bibliography, config)

        # Reread the central bibliography file.
        central = bibtexparser.parse_file(config.bibliography)
        sync_entries(keys, central, local, filename=target)

    if args.operation[0] == "format":
        if target is None:
            target = config.bibliography
        format(filename=target, config=config)


if __name__ == "__main__":
    main()
