# Introduction

The following is a Python script which will parse your `.aux` files looking for the auto-generated code that corresponds to a `\cite` command in your LaTeX. It will look for those keys which resemble either an arXiv identifier, or a MathSciNet identifier.

It will then use
* [`arxiv2bib`](https://github.com/nathangrigg/arxiv2bib)
* [`mr2bib`](https://github.com/bibgetter/mr2bib)
to fetch the corresponding BibTeX entries.

# Examples

There is only one way of using the script, namely by calling

    bibgetter file.aux

where `file.aux` is the auxiliary file created by LaTeX to communicate with `bibtex` or `biber`, and which will contain the information corresponding to the `\cite` commands in your LaTeX file. It is possible to pass multiple files.

The resulting BibTeX code is written to `stdout`, error messages are written to `stderr`.

# Installation

First look at the [installation instructions for `arxiv2bib`](https://github.com/nathangrigg/arxiv2bib).

Then the installation consists of `git clone`'ing this repository and [`mr2bib`](https://github.com/bibgetter/mr2bib) and running `python setup.py install` in both repositories.

For more information, check [bibgetter.github.io](https://bibgetter.github.io).
