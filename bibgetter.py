import os
import sys

import arxiv2bib
import mr2bib

# list of known citation commands
commands = ["citation", "abx@aux@cite"]

class Cli(object):
  """Command line interface"""

  def __init__(self, args=None):
    """Parse arguments"""
    self.args = self.parse_args(args)

    if len(self.args.filenames) == 0:
      self.args.filenames = [line.strip() for line in sys.stdin]

    # avoid duplicate error messages unless verbose is set
    if not self.args.verbose:
      self.args.quiet = True

    self.output = []
    self.messages = []
    self.error_count = 0
    self.code = 0

  def _read(self, f):
    keys = []

    # read the .aux file and look for citation commands
    for line in f:
      # the main assumption here is that the .aux file always contains things of the form \citation{key}, where `citation` can differ
      command = line[1:].split("{")[0]
      if command in commands:
        values = line.split("{")[1].split("}")[0]

        for key in values.split(","): keys.append(key)

    return keys


  def run(self):
    """Produce output and error messages"""
    keys = []

    # collect all citations
    for filename in self.args.filenames:
      try:
        with open(filename) as f: keys = keys + self._read(f)
      except IOError as e:
        print(e)

    bib = []

    # all arXiv keys
    arXiv = filter(arxiv2bib.is_valid, keys)
    bib = bib + [b for b in arxiv2bib.arxiv2bib(arXiv)]

    MR = filter(mr2bib.is_valid, keys)
    try:
      bib = bib + [b for b in mr2bib.mr2bib(MR)]
    except mr2bib.AuthenticationException:
      self.messages.append("Not authenticated to Mathematical Reviews")

    for b in bib:
      if isinstance(b, arxiv2bib.ReferenceErrorInfo) or isinstance(b, mr2bib.ReferenceErrorInfo):
        self.error_count += 1

      else:
        self.output.append(b.bibtex())


  def print_output(self):
    if not self.output:
      return

    output_string = os.linesep.join(self.output)
    try:
      print(output_string)
    except UnicodeEncodeError:
      print_bytes((output_string + os.linesep).encode('utf-8'))
      if self.args.verbose:
        self.messages.append(
         'Could not use system encoding; using utf-8')

  def tally_errors(self, bib):
    """calculate error code"""
    #if self.error_count == len(self.args.filenames):
    #    self.messages.append("No successful matches")
    #    return 2
    if self.error_count > 0:
      self.messages.append("%s of %s matched succesfully" %
       (len(bib) - self.error_count, len(bib)))
      return 1
    else:
      return 0

  def print_messages(self):
    """print messages to stderr"""
    if self.messages:
      self.messages.append("")
      sys.stderr.write(os.linesep.join(self.messages))

  @staticmethod
  def parse_args(args):
    try:
      import argparse
    except:
      sys.exit("Cannot load required module 'argparse'")

    parser = argparse.ArgumentParser(
     description="Create a BibTeX file from the arXiv and Mathematical Reviews API",
     epilog="""\
  Returns 0 on success, 1 on partial failure, 2 on total failure.
  Valid BibTeX is written to stdout, error messages to stderr.
  If no arguments are given, ids are read from stdin, one per line.""",
     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('filenames', metavar='filenames', nargs="*",
     help=".aux filenames")
    parser.add_argument('-q', '--quiet', action='store_true',
     help="Display fewer error messages")
    parser.add_argument('-v', '--verbose', action="store_true",
     help="Display more error messages")

    return parser.parse_args(args)

def main(args=None):
  """Run the command line interface"""
  cli = Cli(args)
  try:
    cli.run()
  except FatalError as err:
    sys.stderr.write(err.args[0] + os.linesep)
    return 2

  cli.print_output()
  cli.print_messages()
  return cli.code


if __name__ == "__main__":
  sys.exit(main())
