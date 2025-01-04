import argparse
import arxiv
import bibtexparser
import fake_useragent
import json
import glob
import os
import re
import requests
import subprocess


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

    return re.match(old, id) or re.match(new, id)


def is_mathscinet_id(id: str) -> bool:
    """
    Check if the given identifier is a valid MathSciNet ID.

    A valid MathSciNet ID starts with `MR` followed by 1 to 7 digits.
    Alternatively, it starts starts with `mr:`, and then a valid MR identifier.
    """
    pattern = r"^(MR|mr:MR)\d{1,7}$"

    return re.match(pattern, id) is not None


def arxiv2biblatex(key, entry):
    """
    Convert an arXiv entry to a BibLaTeX entry.

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
    """
    Extract citation keys from the given file.

    This function searches for citation keys in the provided file content using
    predefined regular expression patterns.

    TODO document the different formats

    Args:
        file (str): The content of the file to search for citation keys.

    Returns:
        list: A list of unique citation keys found in the file.
    """
    # TODO implement other formats
    patterns = [
        re.compile(r"\\abx@aux@cite\{0\}\{([^}]+)\}"),
        re.compile(r"\\abx@aux@cite\{([^}]+)\}"),
    ]
    keys = {key for pattern in patterns for key in pattern.findall(file)}
    return list(keys)


def make_argument_list(func):
    """
    Decorator to convert a single argument to a list if it is a string.

    This is useful for functions that expect a list of arguments, but the user only provides
    a single argument.
    """

    def enclose(argument):
        return func([argument]) if isinstance(argument, str) else func(argument)

    return enclose


@make_argument_list
def get_arxiv(ids):
    # get rid of arXiv: prefix if needed
    ids = [id.split(":")[-1] for id in ids]

    entries = arxiv.Client().results(arxiv.Search(id_list=list(ids)))
    entries = list(map(arxiv2biblatex, ids, entries))

    return "\n".join(entries)


def clean_mr2bib_bibtex(entry):
    to_remove = ()
    if "DOI = {" in entry:
        to_remove = to_remove + ("URL",)
    # other fields (like ISSN, MRREVIEWER, or MRCLASS) I don't like are removed by biber

    lines = entry.strip().splitlines()
    lines = [line for line in lines if not line.lstrip().startswith(to_remove)]

    # if numerical part of key is not 7 characters long we add long version as alternative
    key = lines[0].split("MR")[1][:-1]
    if len(key) < 7:
        # not the cleanest way
        lines = [lines[0]] + [f"  IDS = {{MR{key.rjust(7, "0")}}},"] + lines[1:]

    return "\n".join(lines)


@make_argument_list
def get_mathscinet(ids):
    # TODO make this cleaner, if list of ids is empty, we don't do anything
    if not ids:
        return ""

    # drop the MR from the ids for the API
    ids = [id.lstrip("MR") for id in ids]

    r = requests.get(
        "https://mathscinet.ams.org/mathscinet/api/publications/format",
        params={"formats": "bib", "ids": ",".join(ids)},
        headers={"User-Agent": fake_useragent.UserAgent().chrome},
    )

    # TODO this seems no longer necessary?
    if r.status_code == 401:
        raise Exception("Not authenticated to MathSciNet")

    # anything but 200 means something else went wrong
    if not r.status_code == 200:
        print(r.url)
        raise Exception("Received HTTP status code " + str(r.status_code))

    response = json.loads(r.text)

    return "\n".join(clean_mr2bib_bibtex(entry["bib"]) for entry in response) + "\n"


# pairs of (predicate, action) to resolve the keys
ACTIONS = {
    "arXiv": (is_arxiv_id, get_arxiv),
    "MathSciNet": (is_mathscinet_id, get_mathscinet),
}

# location of the central bibliography file
CENTRAL_BIBLIOGRAPHY = os.path.expanduser("~/.bibgetter/bibliography.bib")


def keys(bibliography) -> list:
    defaults = [entry.key for entry in bibliography.entries]
    alternatives = [
        id
        for entry in bibliography.entries
        if "ids" in entry
        for id in entry["ids"].split(",")
    ]

    return defaults + alternatives


def add_entries(ids, central_keys):
    # take ids, remove the ones already in central_keys, and look up the missing ones
    # ignores local keys (warn user they specified local file)
    missing = [id for id in ids if id not in central_keys]

    for type in ACTIONS:
        (predicate, action) = ACTIONS[type]
        matched = list(filter(predicate, missing))
        missing = [id for id in missing if id not in matched]

        with open(CENTRAL_BIBLIOGRAPHY, "a") as f:
            f.write(action(matched))

        print(f"Added {len(matched)} entries: {matched}")

    print("Entries not matched:", missing)


def sync_entries(ids, central, local_keys, filename=None):
    # take ids, remove the ones already in local_keys, and look up the missing ones
    # from the central bibliography file
    missing = [id for id in ids if id not in local_keys]

    central_keys = [entry.key for entry in central.entries]
    # TODO use keys(central)

    output = ""

    for id in missing:
        if id not in central_keys:
            # TODO need to give a useful error
            print("Entry not found in central bibliography:", id)
            continue

        entry = next(filter(lambda e: e.key == id, central.entries))
        output += entry.raw + "\n"

    # write to local bibliography (if set)
    if filename is not None:
        with open(filename, "a") as f:
            f.write(output)
            # TODO print to stdout that entries were added to the local file (and how many)
    # else, just print to stdout
    else:
        print(output)


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
            "--configfile=sort.conf",
            "--validate-datamodel",
            f"--output_file={filename}",
            filename,
        ]
    )


def main():
    parser = argparse.ArgumentParser(description="bibgetter")
    parser.add_argument("operation", help="Operation to perform", nargs="*")
    parser.add_argument("--file", help=".aux file", type=str)
    parser.add_argument("--local", help="local bibliography file", type=str)
    args = parser.parse_args()

    # read the central bibliography file
    central = bibtexparser.parse_file(CENTRAL_BIBLIOGRAPHY)
    # central_keys = [entry.key for entry in central.entries]
    central_keys = keys(central)

    # read the local bibliography file (if specified)
    local_keys = []
    if args.local:
        local = bibtexparser.parse_file(args.local)
        # TODO use keys
        local_keys = [entry.key for entry in local.entries]

    # the id's of the entries to fetch: commandline arguments and from the .aux file(s)
    ids = []

    # TODO make sure to consistenty use keys and ids?

    # if args.file is present, read the file(s) and look for citations
    if args.file:
        for filename in glob.glob(args.file):
            with open(filename) as f:
                ids.extend(get_citations(f.read()))
                pass

    if args.operation[0] not in ["add", "sync", "pull"]:
        raise (ValueError("Invalid operation"))

    # add the id's from the commandline arguments
    ids.extend(args.operation[1:])

    target = None
    if hasattr(args, "local"):
        target = args.local

    if args.operation[0] == "add":
        add_entries(ids, central_keys)
        format(CENTRAL_BIBLIOGRAPHY)

    if args.operation[0] == "sync":
        sync_entries(ids, central, local_keys, filename=target)

    if args.operation[0] == "pull":
        add_entries(ids, central_keys)
        sync_entries(ids, central, local_keys, filename=target)


if __name__ == "__main__":
    main()
