"""
Cabeceras de seguridad del navegador.

Por qué están aquí y no en un proxy
-----------------------------------
Porque la aplicación sabe lo que necesita y un proxy no. La política se deriva
de cómo se construye el bundle: en producción el CSS sale a un archivo y no hay
`eval`; en desarrollo `style-loader` inyecta `<style>` y el *source map* usa
`eval`. Escribirla aquí evita que alguien la copie a mano en un `nginx.conf` y
se desincronice del build en la primera semana.

Qué acota, y qué no
-------------------
No cierra `OD-15`. El testigo del trabajador sigue viviendo en `sessionStorage`,
que es legible por cualquier script que llegue a ejecutarse en esa página, y
dónde debe vivir es una decisión de CER que estas cabeceras no toman.

Lo que sí hace es **encarecer mucho el único camino que lleva a leerlo**: una
`Content-Security-Policy` sin `unsafe-inline` en `script-src` y sin orígenes
ajenos convierte el XSS reflejado o almacenado en algo que ya no basta con
inyectar. Reducir el radio de una decisión abierta no es cerrarla, y este
módulo no pretende lo contrario.

`Strict-Transport-Security` sólo con HTTPS
-----------------------------------------
Se emite únicamente cuando las cookies ya viajan como `Secure` —es decir, en
producción—. Mandarla desde un `http://cer.localhost` haría que el navegador se
negara a volver a abrir el entorno de desarrollo por HTTP durante meses, y el
daño no lo arregla quitar la cabecera después.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import settings


#: Lo que la aplicación necesita de verdad, sin margen de cortesía.
#:
#: `default-src 'self'` y luego cada directiva que hace falta afinar. No hay
#: ningún origen externo: la aplicación se sirve entera a sí misma, igual que
#: `CORS_ORIGINS` está vacío por el mismo motivo.
_BASE = (
    "default-src 'self'",
    # Sin `unsafe-inline`: las plantillas no llevan JavaScript en línea, así que
    # permitirlo sólo serviría para que un inyector lo aprovechara. Ésta es la
    # directiva que de verdad encarece un XSS, y la que se mantiene estricta.
    "script-src 'self'",
    # `style-src` **sí** lleva `unsafe-inline`, y no por comodidad: medido
    # contra el bundle de producción, abrir un diálogo deja veinte atributos
    # `style` en el documento —Radix bloquea el scroll con `pointer-events`
    # sobre `body`, la barra lateral publica sus anchos como variables CSS— más
    # una etiqueta `<style>` inyectada.
    #
    # Con `style-src 'self'` el navegador los descartaría y los diálogos
    # quedarían rotos **sólo en producción**, que es la peor forma posible de
    # descubrirlo. Permitir estilo en línea no permite ejecutar código: lo que
    # protege del XSS es la directiva de arriba, y ésa no se toca.
    "style-src 'self' 'unsafe-inline'",
    # `data:` para los iconos que el bundle incrusta. `blob:` para las imágenes
    # de documentos (WP-6): se piden a la API con la sesión y se enseñan como
    # URL de objeto, igual que la vista previa de una foto recién hecha, que
    # todavía no ha salido del navegador. Una URL `blob:` sólo la puede crear
    # código de esta misma página.
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    # La aplicación no se enmarca nunca. Es el equivalente moderno de
    # `X-Frame-Options`, que se manda igualmente por los navegadores viejos.
    "frame-ancestors 'none'",
)

#: Lo que el build de desarrollo necesita además.
#:
#: Sólo `eval`, que lo genera `eval-cheap-module-source-map`. Es una propiedad
#: del bundle de desarrollo y no de la aplicación —el de producción no lleva ni
#: un `eval`, comprobado sobre el artefacto compilado—, y por eso la excepción
#: vive aquí y no en la política de producción.
_CONCESIONES_DE_DESARROLLO = {
    "script-src": "'unsafe-eval'",
}


def _politica() -> str:
    directivas = []
    for directiva in _BASE:
        nombre = directiva.split(" ", 1)[0]
        extra = (
            None if settings.is_production
            else _CONCESIONES_DE_DESARROLLO.get(nombre)
        )
        directivas.append(f"{directiva} {extra}" if extra else directiva)
    return "; ".join(directivas)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # Se calcula una vez: la política no depende de la petición.
        self._csp = _politica()

    async def dispatch(self, request, call_next):
        response = await call_next(request)

        cabeceras = response.headers
        cabeceras.setdefault("Content-Security-Policy", self._csp)
        cabeceras.setdefault("X-Content-Type-Options", "nosniff")
        cabeceras.setdefault("X-Frame-Options", "DENY")
        # `same-origin`: la fase 7 comprobó que el `Referer` salía vacío desde la
        # pantalla del trabajador. Esto lo convierte en política en vez de en
        # una casualidad del navegador de turno.
        cabeceras.setdefault("Referrer-Policy", "same-origin")

        if settings.cookie_secure:
            cabeceras.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        return response
