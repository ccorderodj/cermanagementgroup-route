from fastapi import Query
from pydantic import BaseModel

class CommonQueryParams:
    def __init__(
        self,
        page: int = Query(1, ge=1),
        page_size: int = Query(10, ge=1, le=100),
    ):
        self.page = page
        self.page_size = page_size


# class CommonQueryParams(BaseModel):
#     page_size: int = 5
#     page: int = 1
#     # page_size: int = Query(5, ge=1, description="Number of items per page")
#     # page: int = Query(
#     #     1, ge=1, description="Page number. It is first, second etc. page?"
#     # )
