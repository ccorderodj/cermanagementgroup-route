from fastapi import Request
from typing import List, Optional, TypeVar, Generic
from urllib.parse import urlencode, urlunparse, urlparse
import math

T = TypeVar("T")

class Paginator(Generic[T]):
    def __init__(
        self,
        *,
        total_items: int,
        page: int,
        page_size: int,
        results: List[T],
        request: Request
    ):
        self.total_items = total_items
        self.page = page
        self.page_size = page_size
        self.results = results
        self.request = request
        self.total_pages = math.ceil(total_items / page_size)
        self.base_url = self.get_base_url_from_request()

    def get_base_url_from_request(self) -> str:
        """
        Generates a base URL by stripping query parameters from the request URL.
        Includes full scheme + host + path.
        """
        parsed = urlparse(str(self.request.url))
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))

    def _build_url(self, page_number: int) -> str:
        query_params = dict(self.request.query_params)
        query_params.update({
            "page": str(page_number),
            "page_size": str(self.page_size),
        })
        return f"{self.base_url}?{urlencode(query_params)}"

    def get_next_url(self) -> Optional[str]:
        if self.page < self.total_pages:
            return self._build_url(self.page + 1)
        return None

    def get_previous_url(self) -> Optional[str]:
        if self.page > 1:
            return self._build_url(self.page - 1)
        return None

    def to_response(self) -> dict:
        return {
            "count": self.total_items,
            "next": self.get_next_url(),
            "previous": self.get_previous_url(),
            "results": self.results,
        }