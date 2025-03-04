import argparse
import arxiv
import bibtexparser
import fake_useragent
import json
import glob
import os
import re
import rich
import rich.columns
import requests
import subprocess
import sys
import time

BIBGETTER_DIRECTORY = os.path.expanduser("~/.bibgetter")
# location of the central bibliography file
CENTRAL_BIBLIOGRAPHY = os.path.join(BIBGETTER_DIRECTORY, "bibliography.bib")
# location of the central configuration file 
CENTRAL_CONFIGURATION = os.path.join(BIBGETTER_DIRECTORY, "bibgetter.conf")


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

def guess_arxiv_id(id: str) -> str:
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
    """
    pattern = r"^(MR|mr:MR)\d{1,7}$"

    return re.fullmatch(pattern, id) is not None

def guess_mathscinet_id(id: str) -> str:
    """
    Guess the MathSciNet ID from the given identifier.
    Accepts both raw MathSciNet IDs and URLs in various formats.
    """
    if is_mathscinet_id(id):
        return id
    url_pattern = r"^(?:https?://)?mathscinet\.ams\.org/mathscinet/relay-station\?mr=(\d{1,7})$"
    match = re.match(url_pattern, id)
    if match:
        mr_id = f"MR{match.group(1)}"
        if is_mathscinet_id(mr_id):
            return mr_id
    return None

def is_doi(id: str) -> bool:
    """
    Check if the given string is a valid DOI identifier.
    
    DOIs typically start with '10.' followed by a series of numbers,
    then a forward slash and additional characters.
    """
    pattern = r"^(10\.\d{4,9}(/[-._:;()a-zA-Z0-9]+)+)|(10\.1002(/[^\s/]+)+)$"
    return re.fullmatch(pattern, id) is not None

def guess_doi(id: str) -> str:
    """
    Guess the DOI from the given identifier.
    """
    # Extract DOI from URL if needed
    id = re.sub(
        r"^(?:https?://)?(?:dx\.)?doi\.org/(.+)$",
        r"\1",
        id.rstrip("/")
    )
    if is_doi(id):
        return id
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
        f"  ids         = {{{id if key != id else ""}}},\n"
        f"  eprintclass = {{{entry.primary_category}}},\n"
        f"}}\n"
    )


def get_citations(file: str) -> list:
    r"""
    Extract citation keys from the given file.

    This function searches for citation keys in the provided file content using
    predefined regular expression patterns.

    * `\citation{key}`: basic BibTeX
    * `\abx@aux@cite{0}{key}`: current biblatex format

    Args:
        file (str): The content of the file to search for citation keys.

    Returns:
        list: A list of unique citation keys found in the file.
    """
    patterns = [
        re.compile(r"\\citation\{([^}]+)\}"),
        re.compile(r"\\abx@aux@cite\{0\}\{([^}]+)\}"),
    ]
    keys = {key for pattern in patterns for key in pattern.findall(file)}
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

    entries = arxiv.Client().results(arxiv.Search(id_list=list(ids)))
    entries = list(map(arxiv2biblatex, ids, entries))

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
        long = f"{key.rjust(7, "0")}"
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
    # Parse the entry to modify it
    bib = bibtexparser.parse_string(entry)
    entry = bib.entries[0]
    lines = entry.raw.strip().splitlines()
    # Always link to https
    for i, line in enumerate(lines):
        lines[i] = line.replace("http", "https")
    # Fix the key to be equal to the DOI
    lines[0] = lines[0].replace(entry.key, doi)

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
        re.sub(
            r"^(?:https?://)?(?:dx\.)?doi\.org/(.+)$",
            r"\1",
            id.rstrip("/")
        ) for id in ids
    ]

    entries = []
    for doi in ids:
        # TODO: figure out if crossref supports requesting multiple DOIs at once
        url = f"https://api.crossref.org/works/{doi}/transform/application/x-bibtex"
        r = requests.get(
            url,
            headers={"User-Agent": fake_useragent.UserAgent().chrome}
        )
        
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

def id_candidates(id):
    """
    Return a list of possible canonical IDs for the given identifier.
    """
    ids = [id]
    for (_, _, guess) in ACTIONS.values():
        candidate = guess(id)
        if candidate:
            ids.append(candidate)
    return ids

def bibliography_keys(bibliography) -> list:
    if not bibliography:
        return []

    defaults = [entry.key for entry in bibliography.entries]
    alternatives = [
        id
        for entry in bibliography.entries
        if "ids" in entry
        for id in entry["ids"].split(",")
    ]

    return defaults + alternatives


def add_entries(keys, central) -> bool:
    """
    Add entries to the central bibliography.

    Returns the number of items written to the central bibliography.
    """
    # take keys, canonicalize them, remove the ones already in central file, and look up the missing ones
    # ignores local keys
    central_keys = set(bibliography_keys(central))
    missing = [key for key in keys if not any(id in central_keys for id in id_candidates(key))]

    rich.print(
        f"{len(keys) - len(missing)} [default not bold]key(s)"
        f" already in central bibliography"
    )

    if not missing:
        return False

    rich.print(
        f"Looking up {len(missing)} {"entry" if len(missing) == 1 else "entries"}"
    )

    written = []

    for type in ACTIONS:
        (predicate, action, guess) = ACTIONS[type]
        # replace each id with its guessed id if possible
        missing = [guess(id) or id for id in missing]
        matched = list(filter(predicate, missing))
        missing = sorted([id for id in missing if id not in matched])

        if not matched:
            continue

        action_failed = False
        with open(CENTRAL_BIBLIOGRAPHY, "a") as f:
            try:
                f.write(action(matched))
                written.extend(matched)
            except Exception as e:
                action_failed = True
                rich.print(f"[red]Error in retrieving {type} entries")
                rich.print(e)

        if not action_failed:
            rich.print(
                f"Added {len(matched)}"
                f" {"entry" if len(matched) == 1 else "entries"} from {type}"
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


def sync_entries(keys, central, local, filename=None):
    """
    Synchronize entries from central to local

    Returns the number of newly added entries.
    """
    # take keys, remove the ones already in local file, and look up the missing ones
    # from the central bibliography file
    missing = [key for key in keys if key not in bibliography_keys(local)]

    rich.print(f"{len(missing)} [default not bold]key(s) not yet in local file")
    if not len(missing):
        return 0

    entries = []

    for key in missing:
        if key not in bibliography_keys(central):
            rich.print(f"[red]Entry not found in central bibliography: [bold]{key}")
            continue

        for entry in central.entries:
            # the key matches
            if key == entry.key:
                entries.append(entry)
                continue

            # one of the alternative keys matches
            if "ids" in entry and key in entry["ids"].split(","):
                entries.append(entry)
                continue

    # write to local bibliography (if set)
    if filename is not None:
        with open(filename, "a") as f:
            f.write("\n" + "\n\n".join(entry.raw for entry in entries))
            rich.print(
                f"[green]Wrote {len(entries)}"
                f" {"entry" if len(missing) == 1 else "entries"} to local file"
            )

    return len(entries)


def write_configuration():
    # if the central configuration file does not exist, we put it there
    if not os.path.exists(CENTRAL_CONFIGURATION):
        package_directory = os.path.dirname(__file__)
        default = os.path.join(package_directory, "bibgetter.conf")

        os.makedirs(os.path.dirname(CENTRAL_CONFIGURATION), exist_ok=True)
        with open(default, "r") as src, open(CENTRAL_CONFIGURATION, "w") as target:
            target.write(src.read())


def format(filename):
    """
    Format the bibliography file using biber.

    This is like running black on a Python file: an opinionated formattr.
    It will sort the entries, normalize ISBNs, and so on.
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
            f"--configfile={CENTRAL_CONFIGURATION}",
            "--validate-datamodel",
            f"--output_file={filename}",
            filename,
        ],
        stdout=subprocess.DEVNULL,
    )

def get_entries(keys, central):
    """
    Print entries from the central bibliography to stdout.
    If an entry is not found, attempt to add it first.

    Args:
        keys (list): List of bibliography keys to show
        central (BibtexDatabase): The central bibliography database
    """
    # First try to add any missing entries
    touched = add_entries(keys, central)
    if touched:
        format(CENTRAL_BIBLIOGRAPHY)
        # Reload central bibliography with new entries
        central = bibtexparser.parse_file(CENTRAL_BIBLIOGRAPHY)

    for key in keys:
        found = False
        for id in id_candidates(key):
            for entry in central.entries:
                # Check direct key match
                if id == entry.key:
                    print(entry.raw)
                    found = True
                    break
                
                # Check alternative IDs
                if "ids" in entry and id in entry["ids"].split(","):
                    print(entry.raw)
                    found = True
                    break
            if found:
                break
        if not found:
            rich.print(f"[red]Unable to find or add entry: [bold]{key}")


def main(fake_args=None):
    parser = argparse.ArgumentParser(description="bibgetter")
    parser.add_argument("operation", help="Operation to perform (add/sync/pull/get)", nargs="*")
    parser.add_argument("--file", help=".aux file", type=str)
    parser.add_argument("--local", help="local bibliography file", type=str)
    parser.add_argument("--data-directory", help="bibgetter directory location", type=str)
    args = parser.parse_args(fake_args)

    # Update BIBGETTER_DIRECTORY if --data-directory is provided
    global BIBGETTER_DIRECTORY
    if args.data_directory:
        BIBGETTER_DIRECTORY = args.data_directory
        global CENTRAL_BIBLIOGRAPHY, CENTRAL_CONFIGURATION
        CENTRAL_BIBLIOGRAPHY = os.path.join(BIBGETTER_DIRECTORY, "bibliography.bib")
        CENTRAL_CONFIGURATION = os.path.join(BIBGETTER_DIRECTORY, "bibgetter.conf")

    if not args.operation or args.operation[0] not in ["add", "sync", "pull", "get"]:
        if not args.operation:
            rich.print("[red]No operation provided to bibgetter.")
        else:
            rich.print("[red]Invalid operation provided.")
        rich.print("Allowed operations:")
        rich.print("  [green]add[/green]  - Add entries to central bibliography")
        rich.print("  [green]sync[/green] - Sync entries from central to local bibliography")
        rich.print("  [green]pull[/green] - Add entries to central and sync to local bibliography") 
        rich.print("  [green]get[/green]  - Print entries from central bibliography")
        return

    # on first run (and all subsequent runs) of bibgetter, try to write configuration
    write_configuration()

    # read the central bibliography file
    central = None
    try:
        central = bibtexparser.parse_file(CENTRAL_BIBLIOGRAPHY)
    except FileNotFoundError:
        pass

    # read the local bibliography file (if specified)
    local = None
    if args.local:
        try:
            local = bibtexparser.parse_file(args.local)
        except FileNotFoundError:
            pass

    # the keys of the entries to fetch: commandline arguments and from the .aux file(s)
    keys = []

    # if args.file is present, read the file(s) and look for citations
    if args.file:
        for filename in glob.glob(args.file):
            with open(filename) as f:
                keys.extend(get_citations(f.read()))
                pass

    # add the keys from the commandline arguments
    keys.extend(args.operation[1:])
    keys = list(set(keys))

    rich.print(f"Considering {len(keys)} [default not bold]key(s)")

    target = None
    if hasattr(args, "local"):
        target = args.local

    if args.operation[0] == "get":
        # TODO: support local bibliography file here
        get_entries(keys, central)
        return

    if args.operation[0] == "add":
        touched = add_entries(keys, central)
        if touched:
            format(CENTRAL_BIBLIOGRAPHY)

    if args.operation[0] == "sync":
        sync_entries(keys, central, local, filename=target)

    if args.operation[0] == "pull":
        touched = add_entries(keys, central)
        if touched:
            format(CENTRAL_BIBLIOGRAPHY)

        # reread the central bibliography file
        central = bibtexparser.parse_file(CENTRAL_BIBLIOGRAPHY)
        sync_entries(keys, central, local, filename=target)

if __name__ == "__main__":
    main()
