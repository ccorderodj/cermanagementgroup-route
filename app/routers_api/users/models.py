from sqlalchemy import Boolean, Column, DateTime, Integer, String, text
from sqlalchemy.sql import func

from app.core.models.IsActiveMixin import IsActiveMixin
from app.core.models.TimeStamped import TimeStampedModel


class Users(TimeStampedModel, IsActiveMixin):
    """Identidad de plataforma.

    Un usuario **no pertenece a una compañía**: pertenece a la plataforma, y su
    relación con cada compañía vive en `user_company`. Por eso `email` no es
    único —la misma persona puede ser dada de alta por dos tenants distintos—
    aunque `username` sí lo es a nivel global.

    Dos banderas que parecen lo mismo y no lo son (D7):

    * `is_active`     identidad habilitada en la plataforma. En `False` no entra
                      a ninguna parte. Es administración de plataforma.
    * `UserCompany.is_active`  pertenencia a UNA compañía. En `False` no entra a
                      ese tenant, pero sigue existiendo. Es lo que suspende un
                      administrador de tenant.

    `is_superuser` es privilegio de plataforma, no un permiso: no está en el
    catálogo y ninguna API de tenant puede asignarlo (D6).
    """

    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String(254), nullable=False, index=True)
    password = Column(String(255), nullable=True)
    username = Column(String(150), unique=True, nullable=False)
    first_name = Column(String(150), nullable=False)
    last_name = Column(String(150), nullable=False)

    is_superuser = Column(Boolean, nullable=False, server_default=text("false"))
    gender = Column(Boolean, nullable=False, server_default=text("false"))

    last_login = Column(DateTime(timezone=True), nullable=True)
    date_joined = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Recuperación de contraseña (D3). Se guarda el SHA-256 del token, no el
    # token: quien pueda leer esta tabla no obtiene con ello enlaces válidos.
    reset_token_hash = Column(String(64), nullable=True, index=True)
    reset_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # No se declaran relaciones `selectin` hacia `user_company` ni `company`.
    # Las que había cargaban en cascada en cada `find_by_id`, y `find_by_id`
    # corre en toda petición autenticada (AUD-BE-027). Quien necesite la
    # pertenencia la pide explícitamente por `UsersDAO.find_active_membership`.

    def __str__(self) -> str:
        return f"User {self.email}"
