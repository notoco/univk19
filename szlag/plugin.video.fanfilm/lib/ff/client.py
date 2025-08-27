# -*- coding: utf-8 -*-

from __future__ import absolute_import, division, print_function

from typing import Optional, Union, Any, Tuple, List, Dict, overload
from typing_extensions import Literal
import random
import re
import urllib.request as urllib2
from html import unescape
from threading import current_thread

import requests
from requests.auth import HTTPProxyAuth

from lib.ff import cache, dom_parser, control
from lib.ff.workers import ThreadCanceled

urlopen = urllib2.urlopen
Request = urllib2.Request


class RequestHandler:
    _session = None  # Zmienna klasy do przechowywania sesji

    @staticmethod
    def get_session():
        if RequestHandler._session is None:
            RequestHandler._session = requests.Session()
        return RequestHandler._session

    def request(
        self,
        url,
        close=True,
        redirect=True,
        verify=True,
        proxy=None,
        post=None,
        data=None,
        headers=None,
        mobile=False,
        XHR=False,
        limit=None,
        referer=None,
        cookie=None,
        cookies=None,
        compression=False,
        output="",
        timeout=30,
        username=None,
        password=None,
        as_bytes=False,
    ):
        """
        Send an HTTP request and return the desired output.

        Args:
        - url (str): The URL to send the request to.
        - close (bool, optional): Close the session after the request. Defaults to True.
        - redirect (bool, optional): Allow redirects. Defaults to True.
        - verify (bool, optional): Verify SSL certificates. Defaults to True.
        - proxy (str, optional): Proxy server to use.
        - post (dict or str, optional): Data to send in the POST request.
        - data (dict or str, optional): Data payload to send in the request.
        - headers (dict, optional): Additional headers to include in the request.
        - mobile (bool, optional): Use a mobile User-Agent. Defaults to False.
        - XHR (bool, optional): Send the request as an XMLHttpRequest. Defaults to False.
        - limit (int, optional): Limit the size of the response content (in KB).
        - referer (str, optional): Referer header value.
        - cookie (str, optional): Cookie string to include in the headers.
        - cookies (RequestsCookieJar, optional): Cookies to include in the request.
        - compression (bool, optional): Use gzip compression. Defaults to False.
        - output (str, optional): Specifies the type of output ("cookie", "response", etc.). Defaults to raw content.
        - timeout (int, optional): Request timeout. Defaults to 30 seconds.
        - username (str, optional): Username for authentication.
        - password (str, optional): Password for authentication.
        - as_bytes (bool, optional): Return response as bytes. Defaults to False.

        Returns:
        - Depending on the `output` value, it might return raw content, cookies, headers, response object, etc.

        Raises:
        - requests.RequestException: If the request fails.
        """
        if (event := getattr(current_thread(), '_stop_requested', None)) is not None and event.is_set():
            raise ThreadCanceled()
        s = RequestHandler.get_session()

        # Convert URL to text (similar logic)
        url = str(url)

        # Convert post data to bytes
        if isinstance(post, dict):
            post = bytes(requests.compat.urlencode(post), encoding="utf-8")
        elif isinstance(post, str):
            post = bytes(post, encoding="utf-8")

        # Handle authentication
        if username and password:
            if not proxy:
                s.auth = (username, password)
            else:
                s.proxies = {
                    "http": proxy,
                    "https": proxy,
                }
                s.auth = HTTPProxyAuth(username, password)

        # Set headers
        if not headers:
            headers = {}

        # Set User-Agent header based on 'mobile' parameter
        if "User-Agent" not in headers:
            if mobile:
                headers["User-Agent"] = cache.get(randommobileagent, 12, control.providercacheFile)
            else:
                headers["User-Agent"] = cache.get(randomagent, 12, control.providercacheFile)

        if "Referer" not in headers:
            if not referer:
                headers["Referer"] = f"{url.split('/')[0]}//{url.split('/')[2]}/"
            else:
                headers["Referer"] = referer

        headers["Accept-Language"] = headers.get("Accept-Language", "en-US")

        if XHR:
            headers["X-Requested-With"] = "XMLHttpRequest"

        if cookie:
            headers["Cookie"] = cookie

        if compression and not limit:
            headers["Accept-Encoding"] = "gzip"

        # Making the request
        try:
            response = s.request(
                "POST" if (post or data) else "GET",
                url,
                data=post or data,
                headers=headers,
                allow_redirects=redirect,
                timeout=int(timeout),
                verify=verify,
                cookies=cookies,
            )

            # Process the response
            if output == "cookie":
                return "; ".join(
                    [f"{x}={y}" for x, y in response.cookies.get_dict().items()]
                )

            if output == "cookieDict":
                return response.cookies.get_dict()

            elif output == "response":
                content = response.content if limit else response.text
                return (
                    response.status_code,
                    content[: int(limit) * 1024] if limit else content,
                )

            elif output == "chunk":
                return response.content[: 16 * 1024]

            elif output == "extended":
                cookies = "; ".join(
                    [f"{x}={y}" for x, y in response.cookies.get_dict().items()]
                )
                return (
                    response.text if not as_bytes else response.content,
                    response.headers,
                    cookies,
                )

            elif output == "geturl":
                return response.url

            elif output == "headers":
                return response.headers

            elif output == "file_size":
                return len(response.content)

            elif output == "json":
                return response.json()

            else:
                content = response.content if limit else response.text
                return content[: int(limit) * 1024] if limit else content

        except requests.RequestException as e:
            # Handle exceptions
            print(f"Client request failed on url: {url} | Reason: {str(e)}")
            return None

        finally:
            if close:
                s.close()
                RequestHandler._session = None  # Reset session if closed


def request(
    url,
    close=True,
    redirect=True,
    verify=True,
    proxy=None,
    post=None,
    data=None,
    headers=None,
    mobile=False,
    XHR=False,
    limit=None,
    referer=None,
    cookie=None,
    cookies=None,
    compression=False,
    output="",
    timeout=30,
    username=None,
    password=None,
    as_bytes=False,
): # TODO wywalic
    """
    Send an HTTP request and return the desired output.

    Args:
    - url (str): The URL to send the request to.
    - close (bool, optional): Close the session after the request. Defaults to True.
    - redirect (bool, optional): Allow redirects. Defaults to True.
    - verify (bool, optional): Verify SSL certificates. Defaults to True.
    - proxy (str, optional): Proxy server to use.
    - post (dict or str, optional): Data to send in the POST request.
    - data (dict or str, optional): Data payload to send in the request.
    - headers (dict, optional): Additional headers to include in the request.
    - mobile (bool, optional): Use a mobile User-Agent. Defaults to False.
    - XHR (bool, optional): Send the request as an XMLHttpRequest. Defaults to False.
    - limit (int, optional): Limit the size of the response content (in KB).
    - referer (str, optional): Referer header value.
    - cookie (str, optional): Cookie string to include in the headers.
    - cookies (RequestsCookieJar, optional): Cookies to include in the request.
    - compression (bool, optional): Use gzip compression. Defaults to False.
    - output (str, optional): Specifies the type of output ("cookie", "response", etc.). Defaults to raw content.
    - timeout (int, optional): Request timeout. Defaults to 30 seconds.
    - username (str, optional): Username for authentication.
    - password (str, optional): Password for authentication.
    - as_bytes (bool, optional): Return response as bytes. Defaults to False.

    Returns:
    - Depending on the `output` value, it might return raw content, cookies, headers, response object, etc.

    Raises:
    - requests.RequestException: If the request fails.
    """
    if (event := getattr(current_thread(), '_stop_requested', None)) is not None and event.is_set():
        raise ThreadCanceled()

    s = requests.Session()

    # Convert URL to text (similar logic)
    url = str(url)

    # Convert post data to bytes
    if isinstance(post, dict):
        post = bytes(requests.compat.urlencode(post), encoding="utf-8")
    elif isinstance(post, str):
        post = bytes(post, encoding="utf-8")

    # Handle authentication
    if username and password:
        if not proxy:
            s.auth = (username, password)
        else:
            s.proxies = {
                "http": proxy,
                "https": proxy,
            }
            s.auth = HTTPProxyAuth(username, password)

    # Set headers
    if not headers:
        headers = {}

    # Set User-Agent header based on 'mobile' paramete
    if "User-Agent" not in headers:
        if mobile:
            headers["User-Agent"] = cache.get(randommobileagent, 12, control.providercacheFile)
        else:
            headers["User-Agent"] = cache.get(randomagent, 12, control.providercacheFile)

    if "Referer" not in headers:
        if not referer:
            headers["Referer"] = f"{url.split('/')[0]}//{url.split('/')[2]}/"
        else:
            headers["Referer"] = referer

    headers["Accept-Language"] = headers.get("Accept-Language", "en-US")

    if XHR:
        headers["X-Requested-With"] = "XMLHttpRequest"

    if cookie:
        headers["Cookie"] = cookie

    if compression and not limit:
        headers["Accept-Encoding"] = "gzip"

    # Making the request
    try:
        response = s.request(
            "POST" if (post or data) else "GET",
            url,
            data=post or data,
            headers=headers,
            allow_redirects=redirect,
            timeout=int(timeout),
            verify=verify,
            cookies=cookies,
        )

        # Process the response
        if output == "cookie":
            return "; ".join(
                [f"{x}={y}" for x, y in response.cookies.get_dict().items()]
            )

        if output == "cookieDict":
            return response.cookies.get_dict()

        elif output == "response":
            content = response.content if limit else response.text
            return (
                response.status_code,
                content[: int(limit) * 1024] if limit else content,
            )

        elif output == "chunk":
            return response.content[: 16 * 1024]

        elif output == "extended":
            cookies = "; ".join(
                [f"{x}={y}" for x, y in response.cookies.get_dict().items()]
            )
            return (
                response.text if not as_bytes else response.content,
                response.headers,
                cookies,
            )

        elif output == "geturl":
            return response.url

        elif output == "headers":
            return response.headers

        elif output == "file_size":
            return len(response.content)

        elif output == "json":
            return response.json()

        else:
            content = response.content if limit else response.text
            return content[: int(limit) * 1024] if limit else content

    except requests.RequestException as e:
        # Handle exceptions
        print(f"Client request failed on url: {url} | Reason: {str(e)}")
        return None

    finally:
        if close:
            s.close()


@overload
def parseDOM(html: str, name: str, attrs: Optional[Dict[str, str]], ret: Union[Literal[False], str],
             full: Literal[True]) -> List[Tuple[Dict[str, str], str]]: ...


@overload
def parseDOM(html: str, name: str = "", attrs: Optional[Dict[str, str]] = None, ret: Union[Literal[False], str] = False, *,
             full: Literal[True]) -> List[Tuple[Dict[str, str], str]]: ...


@overload
def parseDOM(html: str, name: str = "", attrs: Optional[Dict[str, str]] = None, ret: Union[Literal[False], str] = False,
             full: Literal[False] = False) -> List[str]: ...


def parseDOM(html: str, name: str = "", attrs: Optional[Dict[str, str]] = None, ret: Union[Literal[False], str] = False, full: bool = False) -> Any:
    if attrs:
        rx_attrs = {key: re.compile(value + ("$" if value else ""))
                    for key, value in attrs.items()}
        attrs = rx_attrs  # type: ignore

    results = dom_parser.parse_dom(html, name, attrs, ret)
    if not results:
        return []

    if full:
        results = [(result.attrs, result.content) for result in results]
    elif ret:
        results = [result.attrs[ret.lower()] for result in results]
    else:
        results = [result.content for result in results]

    return results


def replaceHTMLCodes(txt):
    txt = re.sub("(&#[0-9]+)([^;^0-9]+)", "\\1;\\2", txt)
    txt = unescape(txt)
    txt = txt.replace("&quot;", '"')
    txt = txt.replace("&amp;", "&")
    txt = txt.replace("&lt;", "<")
    txt = txt.replace("&gt;", ">")
    txt = txt.replace("&#38;", "&")
    txt = txt.replace("&nbsp;", "")
    txt = txt.replace("&#8230;", "...")
    txt = txt.replace("&#8217;", "'")
    txt = txt.replace("&#8211;", "-")
    txt = txt.strip()
    return txt


def randomagent():
    BR_VERS = [
        ["%s.0" % i for i in range(18, 50)],
        [
            "37.0.2062.103",
            "37.0.2062.120",
            "37.0.2062.124",
            "38.0.2125.101",
            "38.0.2125.104",
            "38.0.2125.111",
            "39.0.2171.71",
            "39.0.2171.95",
            "39.0.2171.99",
            "40.0.2214.93",
            "40.0.2214.111",
            "40.0.2214.115",
            "42.0.2311.90",
            "42.0.2311.135",
            "42.0.2311.152",
            "43.0.2357.81",
            "43.0.2357.124",
            "44.0.2403.155",
            "44.0.2403.157",
            "45.0.2454.101",
            "45.0.2454.85",
            "46.0.2490.71",
            "46.0.2490.80",
            "46.0.2490.86",
            "47.0.2526.73",
            "47.0.2526.80",
            "48.0.2564.116",
            "49.0.2623.112",
            "50.0.2661.86",
            "51.0.2704.103",
            "52.0.2743.116",
            "53.0.2785.143",
            "54.0.2840.71",
            "61.0.3163.100",
        ],
        ["11.0"],
        ["8.0", "9.0", "10.0", "10.6"],
    ]
    WIN_VERS = [
        "Windows NT 10.0",
        "Windows NT 7.0",
        "Windows NT 6.3",
        "Windows NT 6.2",
        "Windows NT 6.1",
        "Windows NT 6.0",
        "Windows NT 5.1",
        "Windows NT 5.0",
    ]
    FEATURES = ["; WOW64", "; Win64; IA64", "; Win64; x64", ""]
    RAND_UAS = [
        "Mozilla/5.0 ({win_ver}{feature}; rv:{br_ver}) Gecko/20100101 Firefox/{br_ver}",
        "Mozilla/5.0 ({win_ver}{feature}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{br_ver} Safari/537.36",
        "Mozilla/5.0 ({win_ver}{feature}; Trident/7.0; rv:{br_ver}) like Gecko",
        "Mozilla/5.0 (compatible; MSIE {br_ver}; {win_ver}{feature}; Trident/6.0)",
    ]
    index = random.randrange(len(RAND_UAS))
    return RAND_UAS[index].format(
        win_ver=random.choice(WIN_VERS),
        feature=random.choice(FEATURES),
        br_ver=random.choice(BR_VERS[index]),
    )


def randommobileagent(mobile):
    _mobagents = [
        "Mozilla/5.0 (Linux; Android 7.1; vivo 1716 Build/N2G47H) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/61.0.3163.98 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; U; Android 6.0.1; zh-CN; F5121 Build/34.0.A.1.247) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/40.0.2214.89 UCBrowser/11.5.1.944 Mobile Safari/537.36",
        "Mozilla/5.0 (Linux; Android 7.0; SAMSUNG SM-N920C Build/NRD90M) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/6.2 Chrome/56.0.2924.87 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 12_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/80.0.3987.95 Mobile/15E148 Safari/605.1",
        "Mozilla/5.0 (iPad; CPU OS 10_2_1 like Mac OS X) AppleWebKit/602.4.6 (KHTML, like Gecko) Version/10.0 Mobile/14D27 Safari/602.1",
    ]

    if mobile == "android":
        return random.choice(_mobagents[:3])
    else:
        return random.choice(_mobagents[3:5])


def agent():
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36"
