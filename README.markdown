# Introduction

`bibgetter` is a tool for mathematicians writing papers in LaTeX,
making bibliography management easier.
You can also read this documentation online
at [`bibgetter.github.io`](htps://bibgetter.github.io).

## Installation

It is best to install it using `pipx`, which is a clean way to install Python applications.

As an end user, the best solution is likely to run

`pipx install git+https://github.com/bibgetter/bibgetter`

As a developer (so this is a reminder to myself, mostly), it is

`pipx install --editable --force .`

## Workflow

There is a central BibLaTeX file, located at `~/.bibgetter/bibliography.bib` which acts as
a central repository for bibliography entries.

### Adding entries

* `bibgetter add` adds entries to the central file in an automated way

One can add entries to this file in the following ways:

1) by hand (and indeed, the whole point is that you curate a single file, once)
2) by specifying arXiv, MathSciNet, or DOI ids or URLs
3) by specifying an .aux file (or files), scanning for bibliography keys being used

An example of the second option:

`bibgetter add 2411.14814 MR1234567 https://doi.org/10.4171/owr/2024/44`

An example of the third option:

`bibgetter add --file article.aux`

If an entry is missing, it will make an API call.

### Accessing entries

* `bibgetter get` prints bibliography entries from the central file

If the entry is not found, it will be automatically added. You can use this to automate
getting bibtex records from the internet in the command line. An example:

`bibgetter get 'https://doi.org/10.1017/is008004024jkt010'`

will print the bibtex record for Rouquier's paper. You can request multiple entries at 
once.


### Transferring entries

* `bibgetter sync` transfers entries from the central file to a local file

It takes as input a list of entries that should exist in the local file, but maybe don't.
It then looks for these in the central file, and if present, copies them to the local file.
It will not overwrite existing entries.

The anticipated use case is the following:

`bibgetter sync --file article.aux --local bibliography.bib`

This option is guaranteed to work offline.

### Both at once

* `bibgetter pull` is the combination of `bibgetter add` and `bibgetter sync`

So most likely you want to have something like

`bibgetter pull --file article.aux --local bibliography.bib`

in your toolchain.

### Adding aliases

* `bibgetter alias` adds aliases for bibliography items to the central file

You can add an alias to an entry by running

`bibgetter alias rouquier-dimension 'https://doi.org/10.1017/is008004024jkt010'

Then you can use `bibgetter get rouquier-dimension` to get the bibtex record for
this paper. The paper will be added to the central file if it is not already there.

Run `bibgetter alias` to print all defined aliases. Advanced operations (editing,
deleting) can only be done by editing the central bibliography file directly.
