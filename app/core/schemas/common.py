from collections.abc import Sequence
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Envoltorio de toda respuesta paginada de la API.

    `page_size` **no** forma parte del contrato: el cliente ya sabe cuál pidió.
    Devolverlo invitaba a que el frontend lo declarara obligatorio —que es
    exactamente lo que hacía, obteniendo `undefined` con tipo `number`
    (AUD-FE-010)—.

    Se retiró también el import de `pydantic.generics.GenericModel`, que quedaba
    de la versión 1 de Pydantic y no se usaba.
    """

    count: int
    results: Sequence[T]
    next: Optional[str] = None
    previous: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
