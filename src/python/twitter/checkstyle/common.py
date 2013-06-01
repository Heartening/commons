from abc import abstractmethod
import ast
import itertools
import tokenize

from twitter.common.lang import Compatibility, Interface


__all__ = (
  'CheckstylePlugin',
  'PythonFile',
  'StyleError',
)


class PythonFile(object):
  """Checkstyle wrapper for Python source files."""

  SKIP_TOKENS = frozenset((tokenize.COMMENT, tokenize.NL, tokenize.DEDENT))

  @classmethod
  def iter_tokens(cls, blob):
    return tokenize.generate_tokens(Compatibility.StringIO(blob).readline)

  @classmethod
  def iter_logical_lines(cls, blob):
    """Returns an iterator of (start_line, stop_line, indent) for logical lines given the source
       blob.
    """
    contents = []
    line_number_start = None

    def translate_logical_line(start, end, contents):
      while contents[0] == '\n':
        start += 1
        contents.pop(0)
      while contents[-1] == '\n':
        end -= 1
        contents.pop()
      return (start, end + 1, len(contents[0]) if contents[0].isspace() else 0)

    for token in cls.iter_tokens(blob):
      token_type, token_text, token_start = token[0:3]
      if token_type in cls.SKIP_TOKENS:
        continue
      contents.append(token_text)
      if line_number_start is None:
        line_number_start = token_start[0]
      elif token_type in (tokenize.NEWLINE, tokenize.ENDMARKER):
        yield translate_logical_line(
            line_number_start,
            token_start[0] + (1 if token_type is tokenize.NEWLINE else -1),
            list(filter(None, contents)))
        contents = []
        line_number_start = None

  @classmethod
  def parse(cls, filename):
    with open(filename) as fp:
      blob = fp.read()
    return cls(blob, filename)

  def __init__(self, blob, filename):
    self._blob = blob
    self._tree = ast.parse(blob, filename)
    self._lines = [None] + list(blob.splitlines())
    self._filename = filename
    self._logical_lines = dict((start, (start, stop, indent))
        for start, stop, indent in self.iter_logical_lines(blob))

  @property
  def filename(self):
    """The filename of this Python file."""
    return self._filename

  @property
  def tokens(self):
    """An iterator over tokens for this Python file from the tokenize module."""
    return self.iter_tokens(self._blob)

  @property
  def logical_lines(self):
    return self._logical_lines

  def __iter__(self):
    return iter(self._lines[1:])

  def line_range(self, line_number):
    if line_number <= 0 or line_number >= len(self._lines):
      raise IndexError('NOTE: Python file line numbers are offset by 1.')
    if line_number not in self.logical_lines:
      return slice(line_number, line_number + 1)
    start, stop, _ = self.logical_lines[line_number]
    return slice(start, stop)

  def __getitem__(self, line_number):
    return self._lines[self.line_range(line_number)]

  def enumerate(self):
    """Return an enumeration of line_number, line pairs."""
    return enumerate(self, 1)

  @property
  def tree(self):
    """The parsed AST of this file."""
    return self._tree


class Nit(object):
  """Encapsulate a Style faux pas."""

  COMMENT = 0
  WARNING = 1
  ERROR = 2

  SEVERITY = {
    COMMENT: 'COMMENT',
    WARNING: 'WARNING',
    ERROR: 'ERROR'
  }

  @classmethod
  def flatten_lines(self, *line_or_line_list):
    return itertools.chain(*line_or_line_list)

  def __init__(self, severity, python_file, message, line_number=None):
    if not severity in self.SEVERITY:
      raise ValueError('Severity should be one of %s' % ' '.join(self.SEVERITY))
    self.python_file = python_file
    self._severity = severity
    self._message = message
    self._line_number = line_number

  @property
  def line_number(self):
    if self._line_number:
      line_range = self.python_file.line_range(self._line_number)
      if line_range.stop - line_range.start > 1:
        return '%03d-%03d' % (line_range.start, line_range.stop - 1)
      else:
        return '%03d' % line_range.start

  @property
  def severity(self):
    return self._severity

  @property
  def message(self):
    return '%-7s %s:%s %s' % (
        self.SEVERITY[self.severity],
        self.python_file.filename,
        self.line_number or '*',
        self._message)

  @property
  def lines(self):
    return self.python_file[self._line_number] if self._line_number else []

  def __str__(self):
    return '\n     |'.join(self.flatten_lines([self.message], self.lines))


class StyleWarning(Nit):
  def __init__(self, *args, **kw):
    super(StyleWarning, self).__init__(Nit.WARNING, *args, **kw)


class StyleError(Nit):
  def __init__(self, *args, **kw):
    super(StyleError, self).__init__(Nit.ERROR, *args, **kw)


class ASTStyleWarning(StyleWarning):
  def __init__(self, python_file, node, message):
    super(ASTStyleWarning, self).__init__(python_file, message, getattr(node, 'lineno', None))


class ASTStyleError(StyleError):
  def __init__(self, python_file, node, message):
    super(ASTStyleError, self).__init__(python_file, message, getattr(node, 'lineno', None))


class CheckstylePlugin(Interface):
  """Interface for checkstyle plugins."""
  def __init__(self, python_file, line_filter=None):
    if not isinstance(python_file, PythonFile):
      raise TypeError('CheckstylePlugin takes PythonFile objects.')
    self.python_file = python_file
    self._affected_lines = None if line_filter is None else list(line_filter())

  def iter_ast_types(self, ast_type):
    for node in ast.walk(self.python_file.tree):
      if isinstance(node, ast_type):
        yield node

  @abstractmethod
  def nits(self):
    """Returns an iterable of Nit pertinent to the enclosed python file."""

  def __iter__(self):
    for nit in self.nits():
      if nit._line_number is None or self._affected_lines is None:
        yield nit
        continue
      nit_slice = self.python_file.line_range(nit._line_number)
      if any(line in self._affected_lines for line in range(nit_slice.start, nit_slice.stop)):
        yield nit

  def errors(self):
    for nit in self:
      if nit.severity is Nit.ERROR:
        yield nit
