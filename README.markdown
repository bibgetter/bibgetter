# Introduction

For more information, check [bibgetter.github.io](https://bibgetter.github.io).


## Workflow

There is a central BibLaTeX file, located at `~/.bibgetter/bibliography.bib` which acts as
a central repository for bibliography entries.

* `bibgetter add` adds entries to the central file in an automated way

One can add entries to this file in the following ways:

1) by hand (and indeed, the whole point is that you curate a single file, once)
2) by specifying arXiv or MathSciNet id's
3) by specifying an .aux file (or files), scanning for bibliography keys being used

An example of the second option: `bibgetter fetch 2411.14814 2410.07620 MR1234567`
An example of the third option: `bibgetter fetch --file article.aux`

If an entry is missing, it will make an API call.

* `bibgetter sync` transfers entries from the central file to a local file

It takes as input a list of entries that should exist in the local file, but maybe don't.
It then looks for these in the central file, and if present, copies them to the local file.

The anticipated use case is the following:

`bibgetter sync --file article.aux --target bibliography.bib`

This option is guaranteed to work offline.

* `bibgetter pull` is the combination of `bibgetter add` and `bibgetter sync`

So most likely you want to have something like

`bibgetter pull --file article.aux --target bibliography.bib`

in your toolchain.