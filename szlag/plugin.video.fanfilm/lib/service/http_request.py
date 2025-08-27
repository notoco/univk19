"""
Request and routes for simple HTTP Proxy for FanFilm Kodi addon.
"""

from typing import Optional, Union, Any, Tuple, List, Dict, Set, Iterable, Mapping
from typing import ClassVar, Type, Callable, TYPE_CHECKING
from typing_extensions import TypeAlias, ParamSpec
import re
# from contextlib import closing
from contextvars import ContextVar, copy_context
from http.server import BaseHTTPRequestHandler
from http import HTTPStatus
from urllib.parse import parse_qsl
import socket  # for socket.timeout for py < 3.10
import json
from traceback import format_exc
from inspect import Signature, signature
from attrs import define, frozen, field, fields
if TYPE_CHECKING:
    from .http_server import Server
    from email.message import Message as HeaderMessage

import requests
import urllib3

from ..ff.log_utils import fflog, fflog_exc
from ..ff.routing import URL  # , Router
from ..ff.types import JsonResult, remove_optional, is_optional
from .misc import JsonEncoder
from const import const

PS = ParamSpec('PS')
RouteResultValue: TypeAlias = Union[JsonResult, str, bytes]
RouteResult: TypeAlias = Union[Tuple[int, RouteResultValue], Tuple[int, RouteResultValue, Optional[Dict[str, str]]], RouteResultValue]

# Disable SSL warnings

urllib3.disable_warnings()
if urllib3.__version__.startswith('1.'):
    urllib3.util.ssl_.DEFAULT_CIPHERS += ':HIGH:!DH:!aNULL'

Host: TypeAlias = str
Port: TypeAlias = int
Address: TypeAlias = Tuple[Host, Port]

# HTTP route dispatchers.
# GET = Router(standalone=True)
# POST = Router(standalone=True)


class HTTPStatusException(Exception):
    def __init__(self, *args, status_code: int = 0, text: Optional[str] = None, data: Optional[JsonResult] = None,
                 headers: Optional[Mapping[str, str]] = None) -> None:
        super().__init__(*args)
        self.status_code = status_code
        self.text = text
        self.data = data
        self.headers = headers


class HTTPBadRequest(HTTPStatusException):
    def __init__(self, *args, status_code: int = 400, message: Optional[str] = None, text: Optional[str] = None, data: Optional[JsonResult] = None) -> None:
        if message is None:
            message = 'bad request'
        if data is None:
            data = {'status': 'error', 'error': message}
        super().__init__(status_code=status_code, *args, data=data, text=text)


class HTTPNotFound(HTTPStatusException):
    def __init__(self, *args, status_code: int = 404, message: Optional[str] = None, text: Optional[str] = None, data: Optional[JsonResult] = None) -> None:
        if message is None:
            message = 'not found'
        if data is None:
            data = {'status': 'error', 'error': message}
        super().__init__(status_code=status_code, *args, data=data, text=text)


class HTTPMethodNotAllowed(HTTPStatusException):
    def __init__(self, *args, status_code: int = 405, message: Optional[str] = None, text: Optional[str] = None, data: Optional[JsonResult] = None,
                 allow: Optional[Iterable[str]] = None) -> None:
        if message is None:
            message = 'method not allowed'
        if data is None:
            data = {'status': 'error', 'error': message}
        headers = {}
        if allow:
            headers['Allow'] = ', '.join(allow)
        super().__init__(status_code=status_code, *args, data=data, text=text, headers=headers)


# class HTTPNotAcceptable(HTTPStatusException):
#     def __init__(self, *args, status_code: int = 406, message: Optional[str] = None, text: Optional[str] = None, data: Optional[JsonResult] = None) -> None:
#         if message is None:
#             message = 'innorect request'
#         if data is None:
#             data = {'status': 'error', 'error': message}
#         super().__init__(status_code=status_code, *args, data=data, text=text)


class HTTPUnprocessableContent(HTTPStatusException):
    def __init__(self, *args, status_code: int = 422, message: Optional[str] = None, text: Optional[str] = None, data: Optional[JsonResult] = None) -> None:
        if message is None:
            message = 'unprocessable content'
        if data is None:
            data = {'status': 'error', 'error': message}
        super().__init__(status_code=status_code, *args, data=data, text=text)


class ExpectedJsonObjectError(HTTPUnprocessableContent):
    def __init__(self, *, message: Optional[str] = None, text: Optional[str] = None, data: Optional[JsonResult] = None) -> None:
        if message is None:
            message = 'expect JSON object'
        super().__init__(data=data, text=text)


@define
class Route:
    """Simple request route for HTTP server."""
    #: HTTP method.
    methods: Set[str]
    #: Function to call.
    call: Callable[..., RouteResult]
    #: Use server refeernece in the call.
    server: bool
    #: Path pattern.
    pattern: re.Pattern
    #: Call method signature.
    signature: Signature

    @classmethod
    def route(cls, method: Union[str, Iterable[str]], path: str) -> Callable[[Callable[PS, RouteResult]], Callable[PS, RouteResult]]:
        """HTTP route decorator."""
        def wrapper(func: Callable[PS, RouteResult]) -> Callable[PS, RouteResult]:
            sig = signature(func)
            first = next(iter(sig.parameters), None)
            # is_server = first == 'self' and func.__module__ == Route.__module__ and func.__qualname__.partition('.')[0] == 'Server'
            is_server = first == 'self' and func.__qualname__.partition('.')[0] == 'Server'
            routes.append(Route(methods=methods, call=func, pattern=re.compile(path), server=is_server, signature=sig))
            return func

        if isinstance(method, str):
            methods = {method}
        else:
            methods = set(method)
        return wrapper

    @classmethod
    def get(cls, path: str) -> Callable[[Callable[PS, RouteResult]], Callable[PS, RouteResult]]:
        """HTTP GET route decorator."""
        return cls.route('GET', path)

    @classmethod
    def post(cls, path: str) -> Callable[[Callable[PS, RouteResult]], Callable[PS, RouteResult]]:
        """HTTP POST route decorator."""
        return cls.route('POST', path)

    @classmethod
    def put(cls, path: str) -> Callable[[Callable[PS, RouteResult]], Callable[PS, RouteResult]]:
        """HTTP PUT route decorator."""
        return cls.route('PUT', path)

    @classmethod
    def patch(cls, path: str) -> Callable[[Callable[PS, RouteResult]], Callable[PS, RouteResult]]:
        """HTTP PATCH route decorator."""
        return cls.route('PATCH', path)

    @classmethod
    def delete(cls, path: str) -> Callable[[Callable[PS, RouteResult]], Callable[PS, RouteResult]]:
        """HTTP PATCH route decorator."""
        return cls.route('DELETE', path)


@frozen(hash=False)
class Request:
    """Simple request route for HTTP server."""
    #: HTTP methid.
    method: str
    #: Request URL.
    url: URL
    #: Called route.
    route: Route
    #: Matched pattern.
    match: re.Match
    #: Match args.
    args: Dict[str, Any]
    #: Query params.
    params: Dict[str, str]
    # Request handler.
    handler: 'RequestHandler'
    #: JSON constent data (e.g. POST body).
    _json: Optional[JsonResult] = field(default=None, hash=False, repr=False, init=False)

    def __bool__(self) -> bool:
        return bool(self.method and self.url)

    @property
    def headers(self) -> 'HeaderMessage':
        if self.handler is None:
            from email.message import Message
            fflog.warning('No handler in Request(), access to no-request?')
            return Message()
        return self.handler.headers

    @property
    def json(self) -> JsonResult:
        """JSON content data (e.g. POST body)."""
        if self._json is None:
            if self.handler is None:
                fflog.warning('No handler in Request(), access to no-request?')
                return {}
            data = self.handler._read_json()
            object.__setattr__(self, '_json', data)
            # fflog(f'HTTP JSON: {data}')
        else:
            data = self._json
        return data

    def _assign(self, request: 'Request') -> None:
        """Force assign values."""
        for f in fields(self.__class__):
            object.__setattr__(self, f.name, getattr(request, f.name))

    @classmethod
    def _empty(cls) -> 'Request':
        """No request."""
        route = Route(methods=set(), call=None, server=False, pattern=None, signature=None)                # type: ignore
        return Request(method='', url=URL(''), route=route, match=None, args={}, params={}, handler=None)  # type: ignore


#: Global always non-request.
no_request: Request = Request._empty()
#: Global current request, only for route methods.
request = no_request
#: Global HTTP routes.
routes: List[Route] = []


class RequestHandler(BaseHTTPRequestHandler):
    """
    A custom HTTP request handler class for handling GET and POST requests.
    """

    DEFAULT_PORT: ClassVar[int] = const.tune.service.http_server.port
    _rx_content_type = re.compile(r'(?P<mime>[-/\w]+)(?:;\scharset=(?P<enc>[-\w]+))?')

    def __init__(self, request, client_address, server, auto_head: bool = True):
        self.server: 'Server'  # type: ignore  -- override server type to our `Server`
        self.http_request: Optional[Request] = None
        self.auto_head: bool = auto_head
        #: Number of request in single connction (connection: keep).
        self.request_count: int = 0
        # NOTE: BaseHTTPRequestHandler.__init__ handle and dispatch request. All initialization must be done before.
        super().__init__(request, client_address, server)

    # def setup(self):
    #     BaseHTTPRequestHandler.setup(self)

    @property
    def url(self) -> URL:
        """Request URL."""
        u = self.server.url
        return URL(f'{u.scheme}://{u.netloc}{self.path}')

    def log_message(self, format, *args):
        """Log an arbitrary message. Override BaseHTTPRequestHandler.log_message."""
        try:
            message = format % args
            if const.tune.service.http_server.verbose >= 1:
                fflog.info(f'{self.address_string()} - - [{self.log_date_time_string()}] {message.translate(self._control_char_table)}', stack_depth=2)
            else:
                fflog.debug(f'{self.address_string()} - - [{self.log_date_time_string()}] {message.translate(self._control_char_table)}', stack_depth=2)
        except Exception:
            pass

    def _output_response(self, data: bytes, /):
        # def iter_content(_bytes):
        #     if _bytes is not None:
        #         yield _bytes

        # for chunk in iter_content(bytes):
        #     self.wfile.write(chunk)
        # if not self.wfile.closed:
        #     self.wfile.write(data)
        try:
            self.wfile.write(data)
        except Exception:
            fflog_exc()

    def _read_content(self) -> bytes:
        """Read input content bytes (POST, PUT, PATCH)."""
        length = int(self.headers.get('Content-Length', 0))
        return self.rfile.read(length)

    def _read_text(self) -> str:
        """Read input content text (POST, PUT, PATCH)."""
        content_type = self.headers.get('Content-Type', '')
        encoding: Optional[str] = None
        if mch := self._rx_content_type.match(content_type):
            encoding = mch['enc'] or None
        return self._read_content().decode(encoding or 'utf-8', errors='ignore')

    def _read_json(self) -> JsonResult:
        """Read input content text (POST, PUT, PATCH)."""
        return json.loads(self._read_text() or '{}')

    def handle_one_request(self) -> None:
        """Parses and dispatchs the request to the appropriate do_*() method."""
        self.protocol_version = "HTTP/1.1"
        self.server_version = 'FanFilmProxyServer/0.1'
        self.request_count += 1

        # Python http/server.py
        try:
            self.raw_requestline = self.rfile.readline(65537)
            if len(self.raw_requestline) > 65536:
                self.requestline = ''
                self.request_version = ''
                self.command = ''
                self.send_error(HTTPStatus.REQUEST_URI_TOO_LONG)
                return
            if not self.raw_requestline:
                self.close_connection = True
                return
            if not self.parse_request():
                # An error code has been sent, just exit
                return
        except (TimeoutError, socket.timeout) as e:
            # a read or a write timed out.  Discard this connection
            # fflog_exc(level=fflog.DEBUG)
            fflog_exc()
            if self.request_count > 1:
                fflog(f'HTTP Request headers timed out: {e!r}, count={self.request_count}')
            else:
                self.log_error(f'Request headers timed out: {e!r}')
            self.close_connection = True
            return

        # try to find route and prepare request
        url = self.url
        if const.tune.service.http_server.verbose >= 2:
            fflog(f'#### FANFILM HTTP: {self.command} {self.path}, {self.headers}')
        self.http_request = None
        method = self.command
        path = url.path
        allow: Set[str] = set()
        auto_head: bool = self.auto_head and method == 'HEAD'
        request: Request = no_request
        for route in routes:
            if mch := route.pattern.fullmatch(path):
                allow.update(route.methods)
                if method in route.methods or (auto_head and 'GET' in route.methods):
                    params = dict(parse_qsl(url.query))
                    request = Request(method, url, match=mch, route=route, args=mch.groupdict(),
                                      params=params, handler=self)
                    self.http_request = request
                    break
        else:
            err = HTTPNotFound()
            return self.response(err.status_code, text=err.text, data=err.data, headers=err.headers, request=request)
        # handle request
        try:
            def prepare_arg(name: str, value: Optional[str]) -> Any:
                if route.signature:
                    if (p := route.signature.parameters.get(name)) and p.annotation:
                        try:
                            if value is None and is_optional(p.annotation):
                                return None
                            typ = remove_optional(p.annotation)
                            if typ is str and value is None:
                                return ''  # special case: need str and got None (from regex)
                            return typ(value)
                        except Exception:
                            pass
                return value

            if request:
                route = request.route
                if const.tune.service.http_server.verbose >= 3 and '/state' in self.path:
                    fflog(f'#### fanfilm HTTP: {self.command} {self.path}: json={json.dumps(request.json)}')
                args = []
                if route.server:
                    args.append(self.server)
                kwargs = {k: prepare_arg(k, v) for k, v in request.args.items()}
                if 'request' in route.call.__globals__:
                    # HACK. Inject global `request` vairable into handler scope.
                    route.call.__globals__['request'] = request
                try:
                    result = route.call(*args, **kwargs)
                finally:
                    if 'request' in route.call.__globals__:
                        route.call.__globals__['request'] = no_request
                status_code = 0
                headers: Optional[Mapping[str, str]] = None
                if isinstance(result, tuple):
                    status_code, result, *ex = result
                    if ex:
                        headers = ex[0]
                if isinstance(result, (str, bytes, bytearray, memoryview)):
                    self.response(status_code=status_code, text=result, headers=headers, head=method == 'HEAD', request=request)
                else:
                    self.response(status_code=status_code, data=result, headers=headers, head=method == 'HEAD', request=request)
            elif allow:
                raise HTTPMethodNotAllowed(allow=allow)
            else:
                raise HTTPNotFound()
            if not self.wfile.closed:
                self.wfile.flush()  # actually send the response if not already done.
        except HTTPStatusException as exc:
            self.response(exc.status_code, text=exc.text, data=exc.data, headers=exc.headers, request=request)
        except TimeoutError as e:
            # a read or a write timed out.  Discard this connection
            self.log_error(f'Request timed out: {e!r}')
            self.close_connection = True
        except Exception:
            fflog_exc()
            try:
                self.response(500, text=f'** EXCEPTION **\n\n{format_exc()}', request=request)
            except Exception:
                pass
        finally:
            # request_var._assign(Request._empty())
            self.wfile.close()

    def response(self, status_code: int = 0, *, text: Optional[Union[str, bytes]] = None, data: Optional[JsonResult] = None,
                 headers: Optional[Mapping[str, str]] = None, head: bool = False, request: Optional[Request] = None) -> None:
        """Server response."""
        if data is not None:
            content = json.dumps(data, cls=JsonEncoder).encode()
            ctype = 'application/json'
        elif text is not None:
            if isinstance(text, str):
                content = text.encode()
            else:
                content = text
            if b'<html' in content[:200]:
                ctype = 'text/html'
            else:
                ctype = 'text/plain'
        else:
            content = None
            ctype = ''

        if headers is None:
            headers = {}
        else:
            headers = dict(headers)
        if content is None:
            self.send_response(status_code or 204)
            headers.setdefault('Content-Length', '0')
            # no 'Content-Type' header for 204
        else:
            self.send_response(status_code or 200)
            if ctype:
                headers.setdefault('Content-Type', ctype)
            headers.setdefault('Content-Length', str(len(content)))
        if headers:
            for header, value in headers.items():
                if value is not None:
                    self.send_header(header, str(value))
        self.end_headers()
        if content and not head:
            self._output_response(content)
        if const.tune.service.http_server.verbose >= 3:
            if request:
                fflog(f'#### FANFILM HTTP: {request.method} {request.url}: {status_code}: {(content or "")[:100]!r}')
            else:
                fflog(f'#### FANFILM HTTP: ??? ???: {status_code}: {(content or "")[:100]!r}')
