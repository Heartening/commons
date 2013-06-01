import tokenize

from ..common import (
    CheckstylePlugin,
    StyleError)


# TODO(wickman) Unless the pep8 module changes to allow for configurable indentation,
# update this to sanitize line continuation styling.
class Indentation(CheckstylePlugin):
  """Enforce proper indentation."""

  INDENT_LEVEL = 2  # the one true way

  def nits(self):
    indents = []

    for token in self.python_file.tokens:
      token_type, token_text, token_start = token[0:3]
      if token_type is tokenize.INDENT:
        last_indent = len(indents[-1]) if indents else 0
        current_indent = len(token_text)
        if current_indent - last_indent != self.INDENT_LEVEL:
          yield StyleError(self.python_file,
              'Indentation of %d instead of %d' % (current_indent - last_indent, self.INDENT_LEVEL),
              token_start[0])
        indents.append(token_text)
      elif token_type is tokenize.DEDENT:
        indents.pop()
