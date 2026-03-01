import pytest
import re
from bibgetter import (
    main,
    is_arxiv_id,
    is_doi,
    is_mathscinet_id,
    guess_arxiv_id,
    guess_doi,
    guess_mathscinet_id,
    substitute_bibtex_key,
    alternative_ids,
    find_entry,
    canonical_id_candidates,
    clean_mathscinet_entry,
    clean_doi_entry,
)
import os
import time
import tempfile
import bibtexparser


def test_help(capsys):
    """Test that help message is displayed correctly"""
    with pytest.raises(SystemExit):
        main(["-h"])
    output = capsys.readouterr().out
    assert "bibgetter" in output
    assert "Operation to perform" in output


def test_no_args(capsys):
    """Test behavior with no arguments"""
    main([])
    output = capsys.readouterr().out
    assert "No" in output
    assert "Allowed operations:" in output
    assert "add" in output
    assert "sync" in output
    assert "pull" in output
    assert "get" in output


@pytest.mark.parametrize(
    "id,expected",
    [
        ("2101.12345", True),
        ("2101.12345v1", True),
        ("arXiv:math/0309136", True),
        ("not-an-arxiv-id", False),
        ("", False),
    ],
)
def test_is_arxiv_id(id, expected):
    """Test arXiv ID validation"""
    assert is_arxiv_id(id) == expected


@pytest.mark.parametrize(
    "id,expected",
    [
        ("10.1007/s00222-021-01074-w", True),
        ("10.4007/annals.2013.178.1.3", True),
        ("not-a-doi", False),
        ("", False),
    ],
)
def test_is_doi(id, expected):
    """Test DOI validation"""
    assert is_doi(id) == expected


@pytest.mark.parametrize(
    "id,expected",
    [
        ("MR3874219", True),
        ("mr:MR3874219", True),
        ("not-a-mr-id", False),
        ("", False),
    ],
)
def test_is_mathscinet_id(id, expected):
    """Test MathSciNet ID validation"""
    assert is_mathscinet_id(id) == expected


@pytest.mark.parametrize(
    "input,expected",
    [
        ("2502.20094", "2502.20094"),
        ("https://arxiv.org/abs/2502.20094", "2502.20094"),
        ("https://arxiv.org/html/2502.19988v1", "2502.19988v1"),
        ("https://arxiv.org/pdf/2502.20094", "2502.20094"),
        ("https://arxiv.org/pdf/2502.20094.pdf", "2502.20094"),
        ("not-an-arxiv-id", None),
    ],
)
def test_guess_arxiv_id(input, expected):
    """Test arXiv ID guessing from various formats"""
    assert guess_arxiv_id(input) == expected


@pytest.mark.parametrize(
    "input,expected",
    [
        ("10.1007/s00222-021-01074-w", "10.1007/s00222-021-01074-w"),
        ("https://doi.org/10.1007/s00222-021-01074-w", "10.1007/s00222-021-01074-w"),
        ("https://dx.doi.org/10.1007/s00222-021-01074-w", "10.1007/s00222-021-01074-w"),
        ("not-a-doi", None),
    ],
)
def test_guess_doi(input, expected):
    """Test DOI guessing from various formats"""
    assert guess_doi(input) == expected


@pytest.mark.parametrize(
    "input,expected",
    [
        ("MR3874219", "MR3874219"),
        ("https://mathscinet.ams.org/mathscinet/relay-station?mr=3874219", "MR3874219"),
        ("not-a-mr-id", None),
    ],
)
def test_guess_mathscinet_id(input, expected):
    """Test MathSciNet ID guessing from various formats"""
    assert guess_mathscinet_id(input) == expected


@pytest.fixture
def temp_bibgetter_dir():
    """Create a temporary directory for bibgetter files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_get_dois(temp_bibgetter_dir, capsys):
    """Test getting DOI entries and saving to central bibliography"""
    # Run get command with two DOIs and custom directory
    main(
        [
            "get",
            "https://doi.org/10.4171/owr/2024/44",
            "10.1307/mmj/20216092",
            "--data-directory",
            temp_bibgetter_dir,
        ]
    )

    output = capsys.readouterr().out
    # Check central bibliography exists and contains entries
    central_bib = os.path.join(temp_bibgetter_dir, "bibliography.bib")
    assert os.path.exists(central_bib)

    # Parse bibliography and check entries
    bib_database = bibtexparser.parse_file(central_bib)
    assert len(bib_database.entries) == 2

    # Verify DOIs are in the entries
    dois = [entry.key for entry in bib_database.entries]
    assert "10.4171/owr/2024/44" in dois
    assert "10.1307/mmj/20216092" in dois


def test_get_dois_with_parentheses(temp_bibgetter_dir, capsys):
    """Test that DOIs with parentheses in them are handled correctly."""
    main(
        [
            "get",
            "https://doi.org/10.1016/S0022-4049(97)00152-7",
            "--data-directory",
            temp_bibgetter_dir,
        ]
    )
    output = capsys.readouterr().out
    # Previously the parentheses were included in the identifier, which caused
    # biber formatting command to stop. We check that this didn't happen by checking
    # that the bibliography record is properly formatted, in particular laid out over
    # several lines.
    lines = output.splitlines()
    # Find the line containing "Keller"
    keller_line = None
    for i, line in enumerate(lines):
        if "Keller" in line:
            keller_line = i
            break
    # Find the line containing "volume"
    volume_line = None
    for i, line in enumerate(lines):
        if "volume" in line:
            volume_line = i
            break
    assert keller_line is not None
    assert volume_line is not None
    assert keller_line != volume_line


def test_get_is_cached(temp_bibgetter_dir, capsys):
    """Test that second get request is faster due to caching"""
    # Run get command first time and measure duration
    start = time.time()
    main(
        [
            "get",
            "https://doi.org/10.4171/owr/2024/44",
            "10.1307/mmj/20216092",
            "--data-directory",
            temp_bibgetter_dir,
        ]
    )
    first_duration = time.time() - start

    # Run same command again and measure duration
    start = time.time()
    main(
        [
            "get",
            "https://doi.org/10.4171/owr/2024/44",
            "10.1307/mmj/20216092",
            "--data-directory",
            temp_bibgetter_dir,
        ]
    )
    second_duration = time.time() - start

    # Second run should be significantly faster since entries are cached
    assert second_duration < first_duration / 2


def test_add_various_ids(temp_bibgetter_dir, capsys):
    """Test adding various IDs to central bibliography"""
    # Run add command with multiple IDs and custom directory
    main(
        [
            "add",
            "https://doi.org/10.4171/owr/2024/44",
            "10.1307/mmj/20216092",
            "https://arxiv.org/abs/2502.20094",
            "https://mathscinet.ams.org/mathscinet/relay-station?mr=4865600",
            "--data-directory",
            temp_bibgetter_dir,
        ]
    )
    output = capsys.readouterr().out
    assert "Error" not in output

    # Check central bibliography exists and contains entries
    central_bib = os.path.join(temp_bibgetter_dir, "bibliography.bib")
    assert os.path.exists(central_bib)

    # Parse bibliography and check number of entries
    bib_database = bibtexparser.parse_file(central_bib)
    assert len(bib_database.entries) == 4


def test_alias(temp_bibgetter_dir, capsys):
    """Test creating and using bibliography key aliases"""
    # First add some entries to work with
    # TODO: avoid network calls here, just provide a pre-made central bibliography file
    main(
        [
            "add",
            "https://doi.org/10.4171/owr/2024/44",
            "10.1307/mmj/20216092",
            "--data-directory",
            temp_bibgetter_dir,
        ]
    )

    # Create aliases
    main(
        [
            "alias",
            "owrpaper",
            "10.4171/owr/2024/44",
            "--data-directory",
            temp_bibgetter_dir,
        ]
    )
    main(
        [
            "alias",
            "mmjpaper",
            "10.1307/mmj/20216092",
            "--data-directory",
            temp_bibgetter_dir,
        ]
    )

    # Check aliases are listed correctly
    main(["alias", "--data-directory", temp_bibgetter_dir])
    output = capsys.readouterr().out
    assert "owrpaper → 10.4171/owr/2024/44" in output
    assert "mmjpaper → 10.1307/mmj/20216092" in output

    # Test getting entries using aliases
    main(["get", "owrpaper", "mmjpaper", "--data-directory", temp_bibgetter_dir])
    output = capsys.readouterr().out
    assert "@article{owrpaper," in output
    assert "@article{mmjpaper," in output


def test_alias_with_guess(temp_bibgetter_dir, capsys):
    """Test that adding an alias to a non-existent bibliography record creates it"""
    main(
        [
            "alias",
            "okawa-irr",
            "https://arxiv.org/abs/2304.14048",
            "--data-directory",
            temp_bibgetter_dir,
        ]
    )
    output = capsys.readouterr().out
    assert "Added alias" in output
    assert "@online{okawa-irr" in output


# ---------------------------------------------------------------------------
# DOI validation – extended
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "id,expected",
    [
        # Typical Springer/Wiley DOIs
        ("10.1007/s00222-021-01074-w", True),
        ("10.4007/annals.2013.178.1.3", True),
        # DOIs with parentheses are valid DOIs (even though they need cleaning
        # before use as a BibTeX key)
        ("10.1016/S0022-4049(97)00152-7", True),
        # Elsevier pii-style DOI
        ("10.1016/j.jalgebra.2022.01.001", True),
        # Short registrant (4 digits) and long (9 digits)
        ("10.1000/xyz123", True),
        ("10.123456789/abc", True),
        # Not valid: missing slash after registrant
        ("10.1234", False),
        # Not valid: registrant has fewer than 4 digits
        ("10.123/abc", False),
        # Not valid: does not start with "10."
        ("not-a-doi", False),
        ("", False),
    ],
)
def test_is_doi_extended(id, expected):
    """Extended DOI-validation tests covering edge-case formats."""
    assert is_doi(id) == expected


def test_guess_doi_parentheses_returns_dict():
    """
    DOIs containing parentheses are valid DOIs but cannot be used as-is as
    BibTeX/BibLaTeX record keys.  ``guess_doi`` must return a dict with both
    ``actual_id`` (the true DOI) and ``bibtex_id`` (the sanitised key).
    """
    doi = "10.1016/S0022-4049(97)00152-7"
    result = guess_doi(doi)
    assert isinstance(result, dict), "Expected a dict for a DOI with parentheses"
    assert result["actual_id"] == doi
    assert "(" not in result["bibtex_id"]
    assert ")" not in result["bibtex_id"]


def test_guess_doi_url_with_parentheses():
    """URL form of a parenthesised DOI should also yield a sanitised bibtex_id."""
    url = "https://doi.org/10.1016/S0022-4049(97)00152-7"
    result = guess_doi(url)
    assert isinstance(result, dict)
    assert "(" not in result["bibtex_id"]


# ---------------------------------------------------------------------------
# substitute_bibtex_key
# ---------------------------------------------------------------------------

_SAMPLE_ENTRY = """\
@article{10.1016/S0022-4049,
  author = {Keller, Bernhard},
  title  = {Derived categories and universal problems},
  ids    = {keller-derived},
}"""


def test_substitute_bibtex_key_changes_key():
    """The record key in the first line is replaced with the requested key."""
    result = substitute_bibtex_key(_SAMPLE_ENTRY, "mykey")
    assert result.startswith("@article{mykey,")


def test_substitute_bibtex_key_old_key_moves_to_ids():
    """
    When the requested key was already an alias in the ids field, substitution
    removes it from ids and places the original primary key there instead,
    keeping the mapping intact.
    """
    entry = (
        "@article{10.1016/S0022-4049,\n"
        "  author = {Keller, Bernhard},\n"
        # 'myalias' is listed as an alternative id
        "  ids    = {myalias, keller-derived},\n"
        "}"
    )
    result = substitute_bibtex_key(entry, "myalias")
    # Primary key is now the alias
    assert result.startswith("@article{myalias,")
    # Original primary key has moved into the ids field
    ids_line = next(
        l for l in result.splitlines() if re.match(r"^\s*ids\s*=", l, re.IGNORECASE)
    )
    assert "10.1016/S0022-4049" in ids_line
    # The alias itself is no longer duplicated in ids
    assert ids_line.count("myalias") == 0


def test_substitute_bibtex_key_uppercase_ids():
    """``IDS`` written in uppercase (manual edit) should be handled correctly."""
    entry = "@article{original-key,\n  IDS = {alias1},\n  title = {foo},\n}"
    result = substitute_bibtex_key(entry, "alias1")
    assert "@article{alias1," in result
    ids_line = next(
        l for l in result.splitlines() if re.match(r"^\s*IDS\s*=", l, re.IGNORECASE)
    )
    assert "original-key" in ids_line


# ---------------------------------------------------------------------------
# alternative_ids – case-insensitive field lookup
# ---------------------------------------------------------------------------


def test_alternative_ids_lowercase():
    """Standard ``ids`` (lowercase) field is returned correctly."""
    bib = bibtexparser.parse_string("@article{key, ids = {a, b, c}}")
    ids = alternative_ids(bib.entries[0])
    assert ids == ["a", "b", "c"]


def test_alternative_ids_uppercase():
    """``IDS`` written in uppercase (from a manual edit) is handled correctly."""
    bib = bibtexparser.parse_string("@article{key, IDS = {x, y}}")
    ids = alternative_ids(bib.entries[0])
    assert ids == ["x", "y"]


def test_alternative_ids_no_ids_field():
    """Entries without an ids field return an empty list."""
    bib = bibtexparser.parse_string("@article{key, title = {No IDs here}}")
    assert alternative_ids(bib.entries[0]) == []


# ---------------------------------------------------------------------------
# find_entry – None-return contract
# ---------------------------------------------------------------------------


def test_find_entry_no_central():
    """find_entry returns None when the central bibliography is None."""
    assert find_entry("anything", None) is None


def test_find_entry_missing_key():
    """find_entry returns None when the key does not exist in the bibliography."""
    bib = bibtexparser.parse_string("@article{existing-key, title = {Foo}}")
    assert find_entry("nonexistent-key", bib) is None


def test_find_entry_by_primary_key():
    """find_entry locates an entry by its primary key."""
    bib = bibtexparser.parse_string("@article{mykey, title = {Bar}}")
    entry = find_entry("mykey", bib)
    assert entry is not None
    assert entry.key == "mykey"


def test_find_entry_by_alias():
    """find_entry locates an entry via its ids/alias field."""
    bib = bibtexparser.parse_string("@article{mykey, ids = {myalias}, title = {Baz}}")
    entry = find_entry("myalias", bib)
    assert entry is not None
    assert entry.key == "mykey"


# ---------------------------------------------------------------------------
# canonical_id_candidates
# ---------------------------------------------------------------------------


def test_canonical_id_candidates_arxiv_url():
    """An arXiv URL expands to the bare ID as a candidate."""
    candidates = canonical_id_candidates("https://arxiv.org/abs/2307.15338")
    assert "2307.15338" in candidates


def test_canonical_id_candidates_doi_url():
    """A doi.org URL expands to the bare DOI as a candidate."""
    candidates = canonical_id_candidates("https://doi.org/10.1007/s00222-021-01074-w")
    assert "10.1007/s00222-021-01074-w" in candidates


def test_canonical_id_candidates_doi_with_parens():
    """A DOI with parentheses produces both the raw DOI and the sanitised key as candidates."""
    doi = "10.1016/S0022-4049(97)00152-7"
    candidates = canonical_id_candidates(doi)
    # The sanitised version (without parentheses) must be a candidate
    assert any("(" not in c for c in candidates)


# ---------------------------------------------------------------------------
# Help-text alignment
# ---------------------------------------------------------------------------


def test_no_args_operations_aligned(capsys):
    """All operation entries in the no-args help text are aligned on the hyphen."""
    main([])
    output = capsys.readouterr().out
    # Collect lines that describe an operation (contain ' - ')
    op_lines = [
        line for line in output.splitlines() if " - " in line and line.startswith("  ")
    ]
    assert len(op_lines) >= 5, "Expected at least 5 operation lines"
    # All hyphens must be at the same column
    positions = [line.index(" - ") for line in op_lines]
    assert (
        len(set(positions)) == 1
    ), f"Operations are not aligned; hyphen positions: {positions}\n" + "\n".join(
        op_lines
    )


# ---------------------------------------------------------------------------
# clean_mathscinet_entry – issue #8: zero-padding short MR numbers
# ---------------------------------------------------------------------------

_MR_SHORT_ENTRY = """\
@article{MR12345,
  author = {Doe, John},
  title  = {Some article},
  year   = {2001},
}"""

_MR_LONG_ENTRY = """\
@article{MR1234567,
  author = {Doe, John},
  title  = {Another article},
  year   = {2001},
}"""


def test_clean_mathscinet_entry_zero_pads_short_key():
    """
    Issue #8: if the numeric part of the MR key is fewer than 7 digits, the key
    must be zero-padded to 7 digits and the short form stored in the IDS field.
    """
    result = clean_mathscinet_entry(_MR_SHORT_ENTRY)
    lines = result.splitlines()
    # The record key on the first line must be the zero-padded form
    assert "MR0012345" in lines[0], f"Expected zero-padded key; got: {lines[0]}"
    # The short form must appear in the IDS field
    ids_line = next(
        (l for l in lines if re.match(r"^\s*IDS\s*=", l, re.IGNORECASE)), None
    )
    assert ids_line is not None, "IDS field missing after zero-padding"
    assert "MR12345" in ids_line


def test_clean_mathscinet_entry_full_key_unchanged():
    """A full 7-digit MR key must not be altered and must not gain an IDS field."""
    result = clean_mathscinet_entry(_MR_LONG_ENTRY)
    lines = result.splitlines()
    assert "MR1234567" in lines[0]
    ids_lines = [l for l in lines if re.match(r"^\s*IDS\s*=", l, re.IGNORECASE)]
    assert len(ids_lines) == 0, "Unexpected IDS field added to already-full MR key"


def test_clean_mathscinet_entry_removes_issn():
    """The ISSN field is stripped from MathSciNet entries."""
    entry = "@article{MR1234567,\n  ISSN   = {0001-5962},\n  title  = {Foo},\n}"
    result = clean_mathscinet_entry(entry)
    assert "ISSN" not in result


def test_clean_mathscinet_entry_removes_url_when_doi_present():
    """If a DOI is present the URL field is redundant and must be removed."""
    entry = (
        "@article{MR1234567,\n"
        "  DOI = {10.1007/foo},\n"
        "  URL = {https://example.com},\n"
        "  title = {Bar},\n"
        "}"
    )
    result = clean_mathscinet_entry(entry)
    assert "URL" not in result
    assert "DOI" in result


# ---------------------------------------------------------------------------
# clean_doi_entry – CrossRef publisher field removal (PR #9 TODO)
# ---------------------------------------------------------------------------

_DOI_ARTICLE_WITH_PUBLISHER = """\
@article{10.1234/foo,
  author    = {Smith, Adam},
  title     = {A paper},
  journal   = {Some Journal},
  year      = {2020},
  publisher = {Elsevier},
}"""

_DOI_BOOK_WITH_PUBLISHER = """\
@book{10.1234/bar,
  author    = {Smith, Adam},
  title     = {A book},
  publisher = {Springer},
  year      = {2020},
}"""


def test_clean_doi_entry_removes_publisher_from_article():
    """
    CrossRef includes ``publisher`` in @article entries; biber's data model
    does not allow this field on articles and raises a validation warning.
    ``clean_doi_entry`` must strip it.
    """
    result = clean_doi_entry(_DOI_ARTICLE_WITH_PUBLISHER, "10.1234/foo")
    assert "publisher" not in result.lower()


def test_clean_doi_entry_keeps_publisher_on_book():
    """``publisher`` is a valid field for @book entries and must be preserved."""
    result = clean_doi_entry(_DOI_BOOK_WITH_PUBLISHER, "10.1234/bar")
    assert "publisher" in result.lower()


def test_clean_doi_entry_sets_key_to_doi():
    """After cleaning, the record key must equal the supplied DOI."""
    result = clean_doi_entry(_DOI_ARTICLE_WITH_PUBLISHER, "10.1234/foo")
    assert result.splitlines()[0].startswith("@article{10.1234/foo,")


def test_clean_doi_entry_upgrades_http_to_https():
    """http:// links must be rewritten to https://."""
    entry = "@article{key, url = {http://example.com}}"
    result = clean_doi_entry(entry, "10.1234/dummy")
    assert "http://" not in result
    assert "https://" in result


# ---------------------------------------------------------------------------
# Issue #12 – arXiv key shuffling
# Integration test: multiple arXiv IDs must be stored under their own key
# ---------------------------------------------------------------------------


def test_arxiv_multiple_ids_correct_keys(temp_bibgetter_dir, capsys):
    """
    Regression for issue #12: when adding several arXiv IDs at once the
    resulting bibliography entries must use the correct key for each paper.
    Specifically, entry.key must equal the arXiv ID that was requested, and the
    ``eprint`` field must hold the true (versioned) arXiv ID of *the same paper*.
    """
    # Use papers whose arXiv IDs are well-known and stable
    ids = ["2307.15338", "1802.06025"]
    main(["add"] + ids + ["--data-directory", temp_bibgetter_dir])
    capsys.readouterr()

    central_bib = os.path.join(temp_bibgetter_dir, "bibliography.bib")
    bib = bibtexparser.parse_file(central_bib)
    assert len(bib.entries) == len(ids), "Expected exactly one entry per requested ID"

    # Build a map key → eprint field for quick lookup
    by_key = {e.key: e for e in bib.entries}

    for id in ids:
        # Each requested ID must appear as a record key
        assert id in by_key, f"Entry for {id!r} missing from bibliography"
        entry = by_key[id]
        # The eprint field must reference the *same* paper (versioned or not)
        eprint_key = next((k for k in entry.fields_dict if k.lower() == "eprint"), None)
        assert eprint_key is not None, f"Entry {id!r} has no eprint field"
        eprint_val = entry[eprint_key]
        # Strip version suffix for comparison
        eprint_bare = re.sub(r"v\d+$", "", eprint_val)
        assert eprint_bare == id or eprint_val.startswith(
            id
        ), f"Entry key {id!r} points to eprint {eprint_val!r} – keys are shuffled!"


# ---------------------------------------------------------------------------
# Issue #5/#7 – central bibliography / configuration created on first run
# ---------------------------------------------------------------------------


def test_central_bibliography_created_on_first_run(temp_bibgetter_dir, capsys):
    """
    Issues #5 and #7: the central bibliography file and the biber configuration
    file must be created automatically when bibgetter is run for the first time.
    """
    central_bib = os.path.join(temp_bibgetter_dir, "bibliography.bib")
    central_conf = os.path.join(temp_bibgetter_dir, "biber-formatting.conf")

    assert not os.path.exists(central_bib), "Pre-condition: bib file must not exist"

    # `add` with an arXiv ID triggers write_configuration() and creates the files
    main(["add", "2307.15338", "--data-directory", temp_bibgetter_dir])
    capsys.readouterr()

    assert os.path.exists(central_bib), "Central bibliography was not created"
    assert os.path.exists(central_conf), "biber configuration file was not created"


# ---------------------------------------------------------------------------
# Issue #1/#3 – only fetch missing items (caching)
# ---------------------------------------------------------------------------


def test_add_does_not_refetch_existing_entries(temp_bibgetter_dir, capsys):
    """
    Issues #1 and #3: adding an entry a second time must not trigger a network
    request.  The output must indicate '1 key already in central bibliography'.
    """
    arxiv_id = "2307.15338"
    main(["add", arxiv_id, "--data-directory", temp_bibgetter_dir])
    capsys.readouterr()  # discard first-run output

    # Second add of the *same* ID
    main(["add", arxiv_id, "--data-directory", temp_bibgetter_dir])
    output = capsys.readouterr().out
    assert "already in central bibliography" in output

    # The bibliography must still contain exactly one entry
    central_bib = os.path.join(temp_bibgetter_dir, "bibliography.bib")
    bib = bibtexparser.parse_file(central_bib)
    assert len(bib.entries) == 1


# ---------------------------------------------------------------------------
# biber formatting – year field must not be converted to date (pbelmans issue)
# ---------------------------------------------------------------------------


def test_format_preserves_year_not_date(temp_bibgetter_dir, capsys):
    """
    After adding an arXiv entry and running the biber formatter, the
    ``year`` field must remain ``year`` and must NOT be renamed to ``date``.
    """
    main(["add", "2307.15338", "--data-directory", temp_bibgetter_dir])
    capsys.readouterr()

    central_bib = os.path.join(temp_bibgetter_dir, "bibliography.bib")
    with open(central_bib) as f:
        content = f.read()

    # The file should contain 'year' and must NOT contain a bare 'date' field
    assert re.search(r"\byear\s*=", content), "year field missing after format"
    assert not re.search(
        r"^\s*date\s*=", content, re.MULTILINE
    ), "biber converted year to date – fix the --output-legacy-dates flag"


def test_format_preserves_journal_not_journaltitle(temp_bibgetter_dir, capsys):
    """
    After adding a DOI-based journal article and running the biber formatter,
    the ``journal`` field must remain ``journal`` and must NOT be renamed to
    ``journaltitle``.
    """
    # Use a stable, well-known DOI for a journal article
    main(["add", "10.1007/s00222-021-01074-w", "--data-directory", temp_bibgetter_dir])
    capsys.readouterr()

    central_bib = os.path.join(temp_bibgetter_dir, "bibliography.bib")
    with open(central_bib) as f:
        content = f.read()

    assert not re.search(
        r"^\s*journaltitle\s*=", content, re.MULTILINE
    ), "biber converted journal to journaltitle – check biber-formatting.conf sourcemap"
