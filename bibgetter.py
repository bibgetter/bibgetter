import argparse
import arxiv
import glob
import re


def is_arxiv(ID):
    pattern = r"^\d{4}\.\d{4,5}(v\d+)?$"
    return re.match(pattern, ID) is not None


def is_mathscinet(ID):
    pattern = r"^MR\d{1,7}$"
    return re.match(pattern, ID) is not None


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
    parser.add_argument("--file", help="File to save the output", type=str)
    args = parser.parse_args()

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
        print(get_arxiv(filter(is_arxiv, IDs)))
        print(list(filter(is_mathscinet, IDs)))


if __name__ == "__main__":
    main()
