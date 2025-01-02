import argparse
import arxiv
import bibtexparser
import glob
import os
import re


def is_arxiv_id(id):
    """
    Check if the given string is a valid arXiv identifier.

    An arXiv identifier follows the pattern: YYYY.NNNN or YYYY.NNNNN,
    optionally followed by 'v' and a version number.

    TODO implement old scheme
    https://info.arxiv.org/help/arxiv_identifier.html
    https://info.arxiv.org/help/arxiv_identifier_for_services.html
    """
    pattern = r"^\d{4}\.\d{4,5}(v\d+)?$"
    return re.match(pattern, id) is not None


def is_mathscinet_id(id):
    """
    Check if the given identifier is a valid MathSciNet ID.

    A valid MathSciNet ID starts with 'MR' followed by 1 to 7 digits.
    """
    pattern = r"^MR\d{1,7}$"
    return re.match(pattern, id) is not None


def arxiv2biblatex(entry):
    id = entry.entry_id.split("/")[-1]
    authors = " and ".join([author.name for author in entry.authors])

    return (
        f"@online{{{id}\n"
        f"  author      = {{{authors}}},\n"
        f"  title       = {{{entry.title}}},\n"
        f"  eprinttype  = {{arxiv}},\n"
        f"  eprint      = {{{id}}},\n"
        f"  eprintclass = {{{entry.primary_category}}},\n"
        f"}}"
    )


def get_arxiv(IDs):
    if isinstance(IDs, str):
        IDs = [IDs]

    entries = arxiv.Client().results(arxiv.Search(id_list=list(IDs)))
    entries = map(arxiv2biblatex, entries)

    for bib in entries:
        print(bib)


def main():
    parser = argparse.ArgumentParser(description="bibgetter")
    parser.add_argument("operation", help="Operation to perform", nargs="*")
    parser.add_argument("--file", help=".aux file", type=str)
    parser.add_argument("--local", help="local bibliography file", type=str)
    args = parser.parse_args()

    # read the central bibliography file
    bib = bibtexparser.parse_file(
        os.path.expanduser("~") + "/.bibgetter/bibliography.bib"
    )
    keys = [entry.key for entry in bib.entries]

    # the IDs of the entries to fetch: commandline arguments and from the .aux file(s)
    IDs = []

    # if args.file is present, read the file(s) and look for citations
    if args.file:
        for filename in glob.glob(args.file):
            with open(filename) as f:
                # TODO look for citations
                pass

    if args.operation[0] in ["fetch", "merge"]:
        IDs.extend(args.operation[1:])

        print(IDs)
        print(list(filter(is_mathscinet, IDs)))
        print(get_arxiv(filter(is_arxiv_id, IDs)))


if __name__ == "__main__":
    main()
