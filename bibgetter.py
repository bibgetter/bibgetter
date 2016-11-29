import os
import sys

import arxiv2bib
import mr2bib

PY2 = sys.version_info[0] == 2
if not PY2:
    from urllib.parse import urlencode
    from urllib.request import urlopen
    from urllib.error import HTTPError
    print_bytes = lambda s: sys.stdout.buffer.write(s)
else:
    from urllib import urlencode
    from urllib2 import HTTPError, urlopen
    print_bytes = lambda s: sys.stdout.write(s)

# list of known citation commands, add as necessary
commands = ["citation", "abx@aux@cite"]

class Cli(object):
  """Command line interface"""

  def __init__(self, args=None):
    """Parse arguments"""
    self.args = self.parse_args(args)

    if len(self.args.filenames) == 0:
      self.args.filenames = [line.strip() for line in sys.stdin]

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
        self.messages.append("Could not open %s" % filename)

    bib = []

    arXiv = set(filter(arxiv2bib.is_valid, keys))
    # arxiv2bib does all keys at once
    bib = bib + [b for b in arxiv2bib.arxiv2bib(arXiv)]

    MR = set(filter(mr2bib.is_valid, keys))
    # mr2bib is key per key
    try:
      bib = bib + [b for b in mr2bib.mr2bib(MR)]
    except mr2bib.AuthenticationException:
      self.messages.append("Not authenticated to Mathematical Reviews")

    for b in bib:
      if isinstance(b, arxiv2bib.ReferenceErrorInfo) or isinstance(b, mr2bib.ReferenceErrorInfo):
        self.error_count += 1

      else:
        self.output.append(b.bibtex())

    self.code = self.tally_errors(bib)


  def print_output(self):
    if not self.output:
      return

    output_string = os.linesep.join(self.output)
    try:
      print(output_string)
    except UnicodeEncodeError:
      print_bytes((output_string + os.linesep).encode('utf-8'))

  def tally_errors(self, bib):
    """calculate error code"""
    if self.error_count > 0:
      self.messages.append("%s of %s keys matched succesfully" % (len(bib) - self.error_count, len(bib)))
      self.messages.append("Not found:")
      for b in bib:
        if isinstance(b, arxiv2bib.ReferenceErrorInfo) or isinstance(b, mr2bib.ReferenceErrorInfo):
          self.messages.append("  %s" % b.id)

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
  Returns 0 on success, 1 on (partial) failure.
  Valid BibTeX is written to stdout, error messages to stderr.
  """,
     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('filenames', metavar='filenames', nargs="*",
     help=".aux filenames")

    return parser.parse_args(args)

def main(args=None):
  """Run the command line interface"""
  cli = Cli(args)
  try:
    cli.run()
  except mr2bib.FatalError or arxiv2bib.FatalError as err:
    sys.stderr.write(err.args[0] + os.linesep)
    return 1

  cli.print_output()
  cli.print_messages()
  return cli.code


if __name__ == "__main__":
  sys.exit(main())
