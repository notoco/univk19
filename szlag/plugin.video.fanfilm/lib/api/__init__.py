from __future__ import annotations
from contextlib import contextmanager
from typing import Optional, Any, Sequence, Iterator, Callable, TypeVar
from typing_extensions import Generic

T = TypeVar('T')

#: Get all pages (depagination).
ALL_PAGES = 0


@contextmanager
def depaginate(api: T, *, limit: Optional[int] = None, max_workers: Optional[int] = None) -> Iterator[T]:
    """
    Depaginate API calls. All called method mast have `page` argument.

    Args:
    api:          object to wrap
    limit:        maximum number of returned items or None
    max_workers:  maximum thread workers

    Example:
    >>> with depaginatate(imdb) as api:
    >>>     all_items = api.list('ls12345')
    """
    from concurrent.futures import ThreadPoolExecutor
    from itertools import chain, islice
    from inspect import signature
    from ..defs import ItemList
    from const import const

    class Wrapper:
        def __getattr__(self, key):
            val = getattr(api, key)
            if callable(val):
                sig = signature(val)
                if (param := sig.parameters.get('page')) and param.kind != param.POSITIONAL_ONLY:
                    def wrapped(*args, **kwargs):
                        page = kwargs.pop('page', None)
                        if page is not None and page != ALL_PAGES:
                            raise TypeError('depaginate() forbids use "page" argument')
                        resp = call(*args, page=1, **kwargs)
                        basket = [resp]
                        if (isinstance(resp, Sequence)
                                and isinstance((page := getattr(resp, 'page', None)), int) and page == 1
                                and isinstance((total := getattr(resp, 'total_pages', None)), int) and total > 1):
                            if not resp:
                                return ItemList.empty()
                            page_size = len(resp)
                            if limit and page_size >= limit:
                                pass
                            elif total == 2:
                                basket.append(call(*args, page=2, **kwargs))
                            else:  # more pages
                                def get(page: int):
                                    return call(*args, page=page, **kwargs)
                                if limit:
                                    total = min(total, (limit + page_size - 1) // page_size)
                                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                                    basket.extend(pool.map(get, range(2, total + 1)))
                            items = chain(*basket)
                            if limit:
                                items = islice(items, limit)
                            return ItemList(items, page=1, total_pages=1)
                    call: Callable[..., Sequence[Any]] = val  # type: ignore[reportAssignmentType]
                    return wrapped
            return val

    if max_workers is None:
        max_workers = const.tune.depagine_max_workers
    yield Wrapper()  # type: ignore[reportReturnType]  # T() wrapper
