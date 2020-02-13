"""
Provides a command line tool to extract citations from an .aux file
and look up the corresponding BibTeX entries from arXiv and MathSciNet
"""

import sys
try:
    from setuptools import setup
except ImportError:
    sys.exit("""Error: Setuptools is required for installation.
 -> http://pypi.python.org/pypi/setuptools""")

setup(
    name = "bibgetter",
    version = "0.1",
    description = "Generate BibTeX entries from arXiv and MathSciNet references in an .aux file",
    author = "Pieter Belmans",
    author_email = "pieterbelmans@gmail.com",
    url = "http://bibgetter.github.io",
    py_modules = ["bibgetter", "requests"],
    keywords = ["mathscinet", "bibtex", "latex", "citation"],
    entry_points = {
        "console_scripts": ["bibgetter = bibgetter:main"]
    },
    license = "BSD",
    classifiers = [
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Science/Research",
        "Topic :: Text Processing :: Markup :: LaTeX",
        "Environment :: Console"
        ],
    long_description = __doc__,
)
