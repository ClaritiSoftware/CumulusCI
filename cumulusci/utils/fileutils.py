import os
import shutil
import urllib.request
import webbrowser
from contextlib import contextmanager
from io import StringIO, TextIOWrapper
from pathlib import Path
from typing import IO, ContextManager, Text, Tuple, Union
from urllib.parse import unquote as urlunquote

import requests

"""Utilities for working with files"""

DataInput = Union[str, IO, Path, "FSResource"]


def _get_path_from_stream(stream):
    "Try to infer a name from an open stream"
    stream_name = getattr(stream, "name", None)
    if isinstance(stream_name, str):
        path = Path(stream_name).absolute()
    else:
        path = getattr(stream, "url", "<stream>")
    return str(path)


@contextmanager
def load_from_source(source: DataInput) -> ContextManager[Tuple[IO[Text], Text]]:
    """Normalize potential data sources into uniform tuple

    Take as input a file-like, path-like, or URL-like
    and convert to a file-like and a string representing
    where it came from. Pass the open file to the loader
    to load the data and then return the result.

    Think of this function as similar to "curl".
    Get data from anywhere easily.

    For example:

    >>> from yaml import safe_load
    >>> with load_from_source("cumulusci.yml") as (file, path):
    ...      print(path)
    ...      print(safe_load(file).keys())
    ...
    cumulusci.yml
    dict_keys(['project', 'sources', 'tasks', 'flows', 'orgs'])

    >>> with load_from_source('http://www.salesforce.com') as (file, path):
    ...     print(path)
    ...     print(file.read(10).strip())
    ...
    http://www.salesforce.com
    <!DOCTYPE

    >>> from urllib.request import urlopen
    >>> with urlopen("https://www.salesforce.com") as f:
    ...     with load_from_source(f) as (file, path):
    ...         print(path)
    ...         print(file.read(10).strip())  #doctest: +ELLIPSIS
    ...
    https://www.salesforce.com/...
    <!DOCTYPE...

    >>> from pathlib import Path
    >>> p = Path(".") / "cumulusci.yml"
    >>> with load_from_source(p) as (file, path):
    ...     print(path)
    ...     print(file.readline().strip())
    ...
    cumulusci.yml
    # yaml-language-server: $schema=cumulusci/schema/cumulusci.jsonschema.json
    """
    if (
        hasattr(source, "read") and hasattr(source, "readable") and source.readable()
    ):  # open file-like
        path = _get_path_from_stream(source)
        if not hasattr(source, "encoding"):  # not decoded yet
            source = TextIOWrapper(source, "utf-8")
        yield source, path
    elif hasattr(source, "open"):  # pathlib.Path-like
        with source.open("rt", encoding="utf-8") as f:
            path = str(source)
            yield f, path
    elif "://" in source:  # URL string-like
        url = source
        resp = requests.get(url)
        resp.raise_for_status()
        yield StringIO(resp.text), url
    else:  # path-string-like
        path = source
        with open(path, "rt", encoding="utf-8") as f:
            yield f, path


def view_file(path):
    """Open the given file in a webbrowser or whatever

    This uses webbrowser.open which might open the file in something other
    than a web browser (eg: a spreadsheet app if you open a .csv file)
    """
    if not isinstance(path, Path):
        path = Path(path)
    url = f"file://{urllib.request.pathname2url(str(path.resolve()))}"
    webbrowser.open(url)


class FSResource:
    """A pathlib.Path-based resource abstraction for local filesystem operations.

    Create them through the open_fs_resource module function or static
    function which will create a context manager that generates an FSResource.

    If you don't need the resource management aspects of the context manager,
    you can call the `new()` classmethod."""

    def __init__(self):
        raise NotImplementedError("Please use open_fs_resource context manager")

    @classmethod
    def new(
        cls,
        resource_url_or_path: Union[str, Path, "FSResource"],
    ):
        """Directly create a new FSResource from a URL or path (absolute or relative)

        You can call this to bypass the context manager in contexts where closing isn't
        important (e.g. interactive repl experiments)."""
        self = cls.__new__(cls)

        if isinstance(resource_url_or_path, FSResource):
            self._path = resource_url_or_path._path
        elif isinstance(resource_url_or_path, str) and "://" in resource_url_or_path:
            url_str = resource_url_or_path
            # Strip the scheme prefix to get the path portion
            _, path_part = url_str.split("://", 1)
            decoded = urlunquote(path_part)
            self._path = Path(decoded).absolute()
        else:
            self._path = Path(resource_url_or_path).absolute()

        return self

    def exists(self):
        return os.path.exists(self._path)

    def open(self, mode="r", **kw):
        return self._path.open(mode, **kw)

    def unlink(self):
        self._path.unlink()

    def rmdir(self):
        self._path.rmdir()

    def removetree(self):
        shutil.rmtree(self._path)

    def getsyspath(self):
        return self._path

    def geturl(self):
        return f"file://{urllib.request.pathname2url(str(self._path))}"

    def joinpath(self, other):
        return FSResource.new(self._path / other)

    def copy_to(self, other):
        if isinstance(other, (str, Path)):
            other = FSResource.new(other)
        shutil.copy2(self._path, other._path)

    def mkdir(self, *, parents=False, exist_ok=False):
        try:
            self._path.mkdir(parents=parents, exist_ok=exist_ok)
        except FileExistsError:
            if not exist_ok:
                raise

    def __contains__(self, other):
        return other in str(self._path)

    @property
    def suffix(self):
        return self._path.suffix

    def __truediv__(self, other):
        return self.joinpath(other)

    def __repr__(self):
        return f"<FSResource {self.geturl()}>"

    def __str__(self):
        return str(self._path)

    def __fspath__(self):
        return str(self._path)

    def close(self):
        pass  # no-op: no filesystem to close

    @staticmethod
    @contextmanager
    def open_fs_resource(
        resource_url_or_path: Union[str, Path, "FSResource"],
    ):
        """Create a context-managed FSResource

        Input is a URL, path (absolute or relative) or FSResource

        The function should be used in a context manager.

        For example:

        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tempdir:
        ...     abspath = Path(tempdir) / "blah"
        ...     with open_fs_resource(abspath) as fs:
        ...         fs.mkdir()
        ...     newfile = fs / "newfile"
        ...     with newfile.open("w") as f:
        ...         _ = f.write("xyzzy")
        ...     with newfile.open("r") as f:
        ...         print(f.read())
        xyzzy

        >>> with open_fs_resource("cumulusci.yml") as cumulusci_yml:
        ...      with cumulusci_yml.open() as c:
        ...          print(c.read(5))
        # yam

        """
        resource = FSResource.new(resource_url_or_path)
        yield resource


open_fs_resource = FSResource.open_fs_resource

if __name__ == "__main__":  # pragma: no cover
    import doctest

    doctest.testmod(report=True)
