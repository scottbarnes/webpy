"""
Web API (wrapper around WSGI)
(from web.py)
"""
from __future__ import annotations

import copy
import pprint
import sys
from collections import defaultdict
from collections.abc import MutableMapping
from http.cookies import CookieError, Morsel, SimpleCookie
from io import BytesIO
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urljoin

from multipart import (
    MultiDict,
    MultipartError,
    MultipartParser,
    MultipartPart,
    parse_options_header,
)

from .utils import dictadd, intget, safestr, storage, storify, threadeddict

__all__ = [
    "config",
    "header",
    "debug",
    "input",
    "data",
    "setcookie",
    "cookies",
    "ctx",
    "HTTPError",
    # 200, 201, 202, 204
    "OK",
    "Created",
    "Accepted",
    "NoContent",
    "ok",
    "created",
    "accepted",
    "nocontent",
    # 301, 302, 303, 304, 307
    "Redirect",
    "Found",
    "SeeOther",
    "NotModified",
    "TempRedirect",
    "redirect",
    "found",
    "seeother",
    "notmodified",
    "tempredirect",
    # 400, 401, 403, 404, 405, 406, 409, 410, 412, 415, 451
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "NoMethod",
    "NotAcceptable",
    "Conflict",
    "Gone",
    "PreconditionFailed",
    "UnsupportedMediaType",
    "UnavailableForLegalReasons",
    "badrequest",
    "unauthorized",
    "forbidden",
    "notfound",
    "nomethod",
    "notacceptable",
    "conflict",
    "gone",
    "preconditionfailed",
    "unsupportedmediatype",
    "unavailableforlegalreasons",
    # 500
    "InternalError",
    "internalerror",
]

config = storage()
config.__doc__ = """
A configuration object for various aspects of web.py.

`debug`
   : when True, enables reloading, disabled template caching and sets internalerror to debugerror.
"""


class HTTPError(Exception):
    def __init__(self, status, headers={}, data=""):
        ctx.status = status
        for k, v in headers.items():
            header(k, v)
        self.data = data
        Exception.__init__(self, status)


def _status_code(status, data=None, classname=None, docstring=None):
    if data is None:
        data = status.split(" ", 1)[1]
    classname = status.split(" ", 1)[1].replace(
        " ", ""
    )  # 304 Not Modified -> NotModified
    docstring = docstring or "`%s` status" % status

    def __init__(self, data=data, headers={}):
        HTTPError.__init__(self, status, headers, data)

    # trick to create class dynamically with dynamic docstring.
    return type(
        classname, (HTTPError, object), {"__doc__": docstring, "__init__": __init__}
    )


ok = OK = _status_code("200 OK", data="")
created = Created = _status_code("201 Created")
accepted = Accepted = _status_code("202 Accepted")
nocontent = NoContent = _status_code("204 No Content")


class Redirect(HTTPError):
    """A `301 Moved Permanently` redirect."""

    def __init__(self, url, status="301 Moved Permanently", absolute=False):
        """
        Returns a `status` redirect to the new URL.
        `url` is joined with the base URL so that things like
        `redirect("about") will work properly.
        """
        newloc = urljoin(ctx.path, url)

        if newloc.startswith("/"):
            if absolute:
                home = ctx.realhome
            else:
                home = ctx.home
            newloc = home + newloc

        headers = {"Content-Type": "text/html", "Location": newloc}
        HTTPError.__init__(self, status, headers, "")


redirect = Redirect


class Found(Redirect):
    """A `302 Found` redirect."""

    def __init__(self, url, absolute=False):
        Redirect.__init__(self, url, "302 Found", absolute=absolute)


found = Found


class SeeOther(Redirect):
    """A `303 See Other` redirect."""

    def __init__(self, url, absolute=False):
        Redirect.__init__(self, url, "303 See Other", absolute=absolute)


seeother = SeeOther


class NotModified(HTTPError):
    """A `304 Not Modified` status."""

    def __init__(self):
        HTTPError.__init__(self, "304 Not Modified")


notmodified = NotModified


class TempRedirect(Redirect):
    """A `307 Temporary Redirect` redirect."""

    def __init__(self, url, absolute=False):
        Redirect.__init__(self, url, "307 Temporary Redirect", absolute=absolute)


tempredirect = TempRedirect


class BadRequest(HTTPError):
    """`400 Bad Request` error."""

    message = "bad request"

    def __init__(self, message=None):
        status = "400 Bad Request"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


badrequest = BadRequest


class Unauthorized(HTTPError):
    """`401 Unauthorized` error."""

    message = "unauthorized"

    def __init__(self, message=None):
        status = "401 Unauthorized"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


unauthorized = Unauthorized


class Forbidden(HTTPError):
    """`403 Forbidden` error."""

    message = "forbidden"

    def __init__(self, message=None):
        status = "403 Forbidden"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


forbidden = Forbidden


class _NotFound(HTTPError):
    """`404 Not Found` error."""

    message = "not found"

    def __init__(self, message=None):
        status = "404 Not Found"
        headers = {"Content-Type": "text/html; charset=utf-8"}
        HTTPError.__init__(self, status, headers, message or self.message)


def NotFound(message=None):
    """Returns HTTPError with '404 Not Found' error from the active application."""
    if message:
        return _NotFound(message)
    elif ctx.get("app_stack"):
        return ctx.app_stack[-1].notfound()
    else:
        return _NotFound()


notfound = NotFound


class NoMethod(HTTPError):
    """A `405 Method Not Allowed` error."""

    message = "method not allowed"

    def __init__(self, cls=None):
        status = "405 Method Not Allowed"
        headers = {}
        headers["Content-Type"] = "text/html"

        methods = ["GET", "HEAD", "POST", "PUT", "DELETE"]
        if cls:
            methods = [method for method in methods if hasattr(cls, method)]

        headers["Allow"] = ", ".join(methods)
        HTTPError.__init__(self, status, headers, self.message)


nomethod = NoMethod


class NotAcceptable(HTTPError):
    """`406 Not Acceptable` error."""

    message = "not acceptable"

    def __init__(self, message=None):
        status = "406 Not Acceptable"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


notacceptable = NotAcceptable


class Conflict(HTTPError):
    """`409 Conflict` error."""

    message = "conflict"

    def __init__(self, message=None):
        status = "409 Conflict"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


conflict = Conflict


class Gone(HTTPError):
    """`410 Gone` error."""

    message = "gone"

    def __init__(self, message=None):
        status = "410 Gone"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


gone = Gone


class PreconditionFailed(HTTPError):
    """`412 Precondition Failed` error."""

    message = "precondition failed"

    def __init__(self, message=None):
        status = "412 Precondition Failed"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


preconditionfailed = PreconditionFailed


class UnsupportedMediaType(HTTPError):
    """`415 Unsupported Media Type` error."""

    message = "unsupported media type"

    def __init__(self, message=None):
        status = "415 Unsupported Media Type"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


unsupportedmediatype = UnsupportedMediaType


class _UnavailableForLegalReasons(HTTPError):
    """`451 Unavailable For Legal Reasons` error."""

    message = "unavailable for legal reasons"

    def __init__(self, message=None):
        status = "451 Unavailable For Legal Reasons"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


def UnavailableForLegalReasons(message=None):
    """Returns HTTPError with '415 Unavailable For Legal Reasons' error from the active application."""
    if message:
        return _UnavailableForLegalReasons(message)
    elif ctx.get("app_stack"):
        return ctx.app_stack[-1].unavailableforlegalreasons()
    else:
        return _UnavailableForLegalReasons()


unavailableforlegalreasons = UnavailableForLegalReasons


class _InternalError(HTTPError):
    """500 Internal Server Error`."""

    message = "internal server error"

    def __init__(self, message=None):
        status = "500 Internal Server Error"
        headers = {"Content-Type": "text/html"}
        HTTPError.__init__(self, status, headers, message or self.message)


def InternalError(message=None):
    """Returns HTTPError with '500 internal error' error from the active application."""
    if message:
        return _InternalError(message)
    elif ctx.get("app_stack"):
        return ctx.app_stack[-1].internalerror()
    else:
        return _InternalError()


internalerror = InternalError


def header(hdr, value, unique=False):
    """
    Adds the header `hdr: value` with the response.

    If `unique` is True and a header with that name already exists,
    it doesn't add a new one.
    """
    hdr, value = safestr(hdr), safestr(value)
    # protection against HTTP response splitting attack
    if "\n" in hdr or "\r" in hdr or "\n" in value or "\r" in value:
        raise ValueError("invalid characters in header")
    if unique is True:
        for h, v in ctx.headers:
            if h.lower() == hdr.lower():
                return

    ctx.headers.append((hdr, value))


class MultipartPartWrapper:
    """
    Ensures calling `.value` on a multipart file object returns the raw value
    in the same way that calling `.value` on FieldStorage multipart objects
    did.

    With MultipartPart, `.value` decodes the data, which will fail with raw
    byte sequences, such as images.

    Additionally, MultipartPart lacks a setter, so it wasn't possible to rebind
    MultipartPart's `.value` method with the `.raw` method. This passes
    through all attribute/method access to the original MultipartPart object,
    save for `.value`, which it intercepts and for which it returns the `.raw`
    method.

    With this, the following code should behave as it did with
    `cgi.FieldStorage`:

    class ImageUpload:
        def POST(self, path):
            i = web.input(file={})
            name, filename, value = i.file.name, i.file.filename, i.file.value
    """

    def __init__(self, part: MultipartPart) -> None:
        self._part = part

    def __getattr__(self, name: str) -> Any:
        """
        Return raw data when accessing the list property, or otherwise pass
        the request through.
        """
        if name == "value":
            return self._part.raw

        return getattr(self._part, name)


def parse_multipart_data(
    stream: BytesIO, boundary: str, content_length: int, **kwargs
) -> tuple[MutableMapping, MutableMapping]:
    """
    For compatibility with cgi.FieldStorage, if all uploads use the
    same name, then put them under in list under a single key. E.g.:
    {'file': [<file_object_1>, <file_object_2>]}
    But if the files use different keys, just put each object under
    its own key. E.g.:
    {'file_1': <file_object_1>, 'file_2': <file_object_2>}
    """
    files = defaultdict(list)
    forms = defaultdict(list)

    for part in MultipartParser(stream, boundary, content_length, **kwargs):
        if part.filename or not part.is_buffered():
            files[part.name].append(part)
        else:
            forms[part.name].append(part.value)

    # Flatten lists with only one item for cgi.FieldStorage compatibility.
    forms = flatten_list(forms)
    files = flatten_list(files)

    # Wrap output for compatibility with cgi.FieldStorage's value method.
    for key, part in files.items():
        if isinstance(part, list):
            files[key] = [MultipartPartWrapper(item) for item in part]
        else:
            files[key] = MultipartPartWrapper(part)

    return forms, files


def custom_parse_form_data(
    environ: dict, charset: str = "utf8", strict: bool = False, **kwargs
) -> tuple[MutableMapping, MutableMapping]:
    """
    The same as multipart.parse_form_data, but with cgi.FieldStorage backwards
    compatibility.

    This always executes MultipartPartWrapper and prevents parse_form_data
    from clobbering files when every file has the same name attribute.

    Code adapted directly from multipart.parse_form_data.

    See the tests for examples of the input and output.
    """
    forms, files = MultiDict(), MultiDict()

    try:
        if environ.get("REQUEST_METHOD", "GET").upper() not in ("POST", "PUT"):
            raise MultipartError("Request method other than POST or PUT.")
        content_length = int(environ.get("CONTENT_LENGTH", "-1"))
        content_type = environ.get("CONTENT_TYPE", "")

        if not content_type:
            raise MultipartError("Missing Content-Type header.")

        content_type, options = parse_options_header(content_type)
        stream = environ.get("wsgi.input") or BytesIO()
        kwargs["charset"] = charset = options.get("charset", charset)

        if content_type == "multipart/form-data":
            boundary = options.get("boundary", "")

            if not boundary:
                raise MultipartError("No boundary for multipart/form-data.")
            forms, files = parse_multipart_data(
                stream, boundary, content_length, **kwargs
            )

        else:
            raise MultipartError("Unsupported content type.")

    except MultipartError:
        if strict:
            for part in files.values():
                part.close()
            raise

    return forms, files


def flatten_list(data: MutableMapping[str, Any]) -> MutableMapping:
    """
    Ensure output matches Python's cgi.FieldStorage handling for
    query parameters.

    >>> flatten_list({'x': ['2'], 'y': ['1', '2']})
    {'x': '2', 'y': ['1', '2']}
    """
    data_copy = copy.copy(data)

    for k, v in data_copy.items():
        if len(v) == 1:
            data_copy[k] = v[0]

    return data_copy


def rawinput(method: str | None = None) -> storage:
    """Returns storage object with GET or POST arguments."""
    method = method or "both"
    env = ctx.env.copy()
    post_req = get_req = {}

    if method.lower() in ["both", "post", "put", "patch"]:
        if env["REQUEST_METHOD"] in ["POST", "PUT", "PATCH"]:
            if env.get("CONTENT_TYPE", "").lower().startswith("multipart/"):
                # Since wsgi.input is directly passed to cgi.FieldStorage,
                # it cannot be called multiple times. Saving the FieldStorage
                # object in ctx to allow calling web.input multiple times.
                post_req = ctx.get("_fieldstorage")
                if not post_req:
                    # 'empty' calls to cgi.FieldStorage returned an empty dict.
                    try:
                        forms, files = custom_parse_form_data(environ=env, strict=True)
                        post_req = dictadd(forms, files)
                        ctx._fieldstorage = post_req
                    except IndexError:
                        post_req = {}

            else:
                post_data = data().decode("utf-8")
                post_req = parse_qs(post_data, keep_blank_values=True)
                post_req = flatten_list(post_req)

    if method.lower() in ["both", "get"]:
        env["REQUEST_METHOD"] = "GET"
        get_req = parse_qs(env.get("QUERY_STRING", ""), keep_blank_values=True)
        get_req = flatten_list(get_req)

    return storage(dictadd(get_req, post_req))


def input(*requireds, **defaults):
    """
    Returns a `storage` object with the GET and POST arguments.
    See `storify` for how `requireds` and `defaults` work.
    """
    _method = defaults.pop("_method", "both")
    out = rawinput(_method)
    try:
        defaults.setdefault("_unicode", True)  # force unicode conversion by default.
        return storify(out, *requireds, **defaults)
    except KeyError:
        raise badrequest()


def data():
    """Returns the data sent with the request."""
    if "data" not in ctx:
        if ctx.env.get("HTTP_TRANSFER_ENCODING") == "chunked":
            ctx.data = ctx.env["wsgi.input"].read()
        else:
            cl = intget(ctx.env.get("CONTENT_LENGTH"), 0)
            ctx.data = ctx.env["wsgi.input"].read(cl)
    return ctx.data


def setcookie(
    name,
    value,
    expires="",
    domain=None,
    secure=False,
    httponly=False,
    path=None,
    samesite=None,
):
    """Sets a cookie."""
    morsel = Morsel()
    name, value = safestr(name), safestr(value)
    morsel.set(name, value, quote(value))
    if isinstance(expires, int) and expires < 0:
        expires = -1000000000
    morsel["expires"] = expires
    morsel["path"] = path or ctx.homepath + "/"
    if domain:
        morsel["domain"] = domain
    if secure:
        morsel["secure"] = secure
    if httponly:
        morsel["httponly"] = True
    value = morsel.OutputString()
    if samesite and samesite.lower() in ("strict", "lax", "none"):
        value += "; SameSite=%s" % samesite
    header("Set-Cookie", value)


def parse_cookies(http_cookie):
    r"""Parse a HTTP_COOKIE header and return dict of cookie names and decoded values.

    >>> sorted(parse_cookies('').items())
    []
    >>> sorted(parse_cookies('a=1').items())
    [('a', '1')]
    >>> sorted(parse_cookies('a=1%202').items())
    [('a', '1 2')]
    >>> sorted(parse_cookies('a=Z%C3%A9Z').items())
    [('a', 'Z\xc3\xa9Z')]
    >>> sorted(parse_cookies('a=1; b=2; c=3').items())
    [('a', '1'), ('b', '2'), ('c', '3')]

    # TODO: cclauss re-enable this test
    # >>> sorted(parse_cookies('a=1; b=w("x")|y=z; c=3').items())
    # [('a', '1'), ('b', 'w('), ('c', '3')]

    >>> sorted(parse_cookies('a=1; b=w(%22x%22)|y=z; c=3').items())
    [('a', '1'), ('b', 'w("x")|y=z'), ('c', '3')]

    >>> sorted(parse_cookies('keebler=E=mc2').items())
    [('keebler', 'E=mc2')]
    >>> sorted(parse_cookies(r'keebler="E=mc2; L=\"Loves\"; fudge=\012;"').items())
    [('keebler', 'E=mc2; L="Loves"; fudge=\n;')]
    """
    # print "parse_cookies"
    if '"' in http_cookie:
        # HTTP_COOKIE has quotes in it, use slow but correct cookie parsing
        cookie = SimpleCookie()
        try:
            cookie.load(http_cookie)
        except CookieError:
            # If HTTP_COOKIE header is malformed, try at least to load the cookies we can by
            # first splitting on ';' and loading each attr=value pair separately
            cookie = SimpleCookie()
            for attr_value in http_cookie.split(";"):
                try:
                    cookie.load(attr_value)
                except CookieError:
                    pass
        cookies = {k: unquote(v.value) for k, v in cookie.items()}
    else:
        # HTTP_COOKIE doesn't have quotes, use fast cookie parsing
        cookies = {}
        for key_value in http_cookie.split(";"):
            key_value = key_value.split("=", 1)
            if len(key_value) == 2:
                key, value = key_value
                cookies[key.strip()] = unquote(value.strip())
    return cookies


def cookies(*requireds, **defaults):
    """Returns a `storage` object with all the request cookies in it.

    See `storify` for how `requireds` and `defaults` work.

    This is forgiving on bad HTTP_COOKIE input, it tries to parse at least
    the cookies it can.

    The values are converted to unicode if _unicode=True is passed.
    """
    # parse cookie string and cache the result for next time.
    if "_parsed_cookies" not in ctx:
        http_cookie = ctx.env.get("HTTP_COOKIE", "")
        ctx._parsed_cookies = parse_cookies(http_cookie)

    try:
        return storify(ctx._parsed_cookies, *requireds, **defaults)
    except KeyError:
        badrequest()
        raise StopIteration()


def debug(*args):
    """
    Prints a prettyprinted version of `args` to stderr.
    """
    try:
        out = ctx.environ["wsgi.errors"]
    except:
        out = sys.stderr
    for arg in args:
        print(pprint.pformat(arg), file=out)
    return ""


def _debugwrite(x):
    try:
        out = ctx.environ["wsgi.errors"]
    except:
        out = sys.stderr
    out.write(x)


debug.write = _debugwrite

ctx = context = threadeddict()

ctx.__doc__ = """
A `storage` object containing various information about the request:

`environ` (aka `env`)
   : A dictionary containing the standard WSGI environment variables.

`host`
   : The domain (`Host` header) requested by the user.

`home`
   : The base path for the application.

`ip`
   : The IP address of the requester.

`method`
   : The HTTP method used.

`path`
   : The path request.

`query`
   : If there are no query arguments, the empty string. Otherwise, a `?` followed
     by the query string.

`fullpath`
   : The full path requested, including query arguments (`== path + query`).

### Response Data

`status` (default: "200 OK")
   : The status code to be used in the response.

`headers`
   : A list of 2-tuples to be used in the response.

`output`
   : A string to be used as the response.
"""

if __name__ == "__main__":
    import doctest

    doctest.testmod()
