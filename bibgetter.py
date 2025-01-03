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


def sanitize_mathscinet_id(id):
    """
    Sanitize a MathSciNet ID by removing leading zeroes
    """
    return re.sub(r"^MR0+", "MR", id)


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


def get_citations(file):
    # TODO implement other formats
    pattern = re.compile(r"\\abx@aux@cite\{0\}\{([^}]+)\}")
    return list(set(pattern.findall(file)))


def make_argument_list(func):
    """
    Decorator to convert a single argument to a list if it is a string.

    This is useful for functions that expect a list of arguments, but the user only provides
    a single argument.
    """

    def enclose(argument):
        if isinstance(argument, str):
            return func([argument])
        func(argument)

    return enclose


@make_argument_list
def get_arxiv(ids):
    entries = arxiv.Client().results(arxiv.Search(id_list=list(ids)))
    entries = map(arxiv2biblatex, entries)

    return "\n".join(entries)


@make_argument_list
def get_mathscinet(ids):
    # TODO implement this
    return ""


def main():
    parser = argparse.ArgumentParser(description="bibgetter")
    parser.add_argument("operation", help="Operation to perform", nargs="*")
    parser.add_argument("--file", help=".aux file", type=str)
    parser.add_argument("--local", help="local bibliography file", type=str)
    args = parser.parse_args()

    # read the central bibliography file
    central = bibtexparser.parse_file(
        os.path.expanduser("~") + "/.bibgetter/bibliography.bib"
    )
    central_keys = [entry.key for entry in central.entries]

    # read the local bibliography file (if specified)
    local_keys = []
    if args.local:
        local = bibtexparser.parse_file(args.local)
        local_keys = [entry.key for entry in local.entries]

    # the id's of the entries to fetch: commandline arguments and from the .aux file(s)
    ids = []

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

    if args.operation[0] == "add":
        # take ids, remove the ones already in central_keys, and look up the missing ones
        # ignores local keys (warn user they specified local file)
        missing = [id for id in ids if id not in central_keys]
        print("missing ids are")
        print(missing)
        actions = [(is_arxiv_id, get_arxiv), (is_mathscinet_id, get_mathscinet)]

        for predicate, action in actions:
            print(predicate)
            print(list(map(action, filter(predicate, missing))))
    if args.operation[0] == "sync":
        pass
    if args.operation[0] == "pull":
        pass

    # print(get_arxiv(filter(is_arxiv_id, ids)))
    # print(list(filter(is_mathscinet_id, ids)))


if __name__ == "__main__":
    main()
