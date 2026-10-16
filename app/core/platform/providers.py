"""
Integraciones de terceros, sus proveedores y la guía para configurarlos.

Una sola fuente (D12-04)
------------------------
Settings no escribe sus guías a mano. Todo lo que la pantalla enseña —qué
proveedor elegir, dónde se consigue cada credencial, qué campo la recibe, de
qué tipo es— sale de aquí, y la API lo valida con lo mismo. Si la guía y la
validación vivieran en sitios distintos, la pantalla acabaría pidiendo un campo
que el servidor rechaza.

Las rutas de consola y los pasos se verificaron contra la documentación de cada
proveedor el 10 de septiembre de 2026; los enlaces van en `docs`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class FieldKind(StrEnum):
    """Qué clase de dato es. Es lo que la guía enseña junto a cada campo."""

    PUBLIC_IDENTIFIER = "public_identifier"
    SECRET = "secret"
    ENDPOINT = "endpoint"
    MAILBOX = "mailbox"
    CHOICE = "choice"
    POLICY = "policy"
    PRESET = "preset"


GUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
HOSTNAME = r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$"
HTTPS_URL = r"^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?(/.*)?$"
BUCKET = r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"
PORT = r"^[0-9]{1,5}$"


@dataclass(frozen=True)
class ProviderField:
    name: str
    label: str
    kind: FieldKind
    #: De dónde sale, en términos de la consola del proveedor.
    source: str
    #: Cómo es el valor, para quien lo va a pegar.
    format: str = ""
    required: bool = True
    default: str | int | bool | None = None
    choices: tuple[str, ...] = ()
    pattern: str | None = None
    #: Si caduca: la guía pide la fecha y el planificador avisa antes.
    expires: bool = False

    @property
    def secret(self) -> bool:
        return self.kind == FieldKind.SECRET


@dataclass(frozen=True)
class GuideStep:
    text: str
    link: str | None = None


@dataclass(frozen=True)
class DocLink:
    label: str
    url: str


@dataclass(frozen=True)
class Provider:
    key: str
    title: str
    summary: str
    #: Quién, en CER, suele tener acceso para conseguir las credenciales.
    who: str
    steps: tuple[GuideStep, ...]
    fields: tuple[ProviderField, ...]
    recommended: bool = False
    #: `False` = se documenta pero no se puede configurar todavía.
    available: bool = True
    warnings: tuple[str, ...] = ()
    docs: tuple[DocLink, ...] = ()

    def field(self, name: str) -> ProviderField | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def secret_fields(self) -> tuple[ProviderField, ...]:
        return tuple(f for f in self.fields if f.secret)

    @property
    def config_fields(self) -> tuple[ProviderField, ...]:
        return tuple(f for f in self.fields if not f.secret)


@dataclass(frozen=True)
class Integration:
    key: str
    title: str
    summary: str
    #: Si producción la necesita. Obligatoria sin verificar = gate abierto.
    required: bool
    providers: tuple[Provider, ...]
    open_decision: str | None = None
    #: La comprobación de Diagnostics que la demuestra. `None` = no hay ninguna.
    capability_key: str | None = None

    def provider(self, key: str | None) -> Provider | None:
        return next((p for p in self.providers if p.key == key), None)


# ══ Correo ═══════════════════════════════════════════════════════════════════

_M365 = Provider(
    key="m365_oauth",
    title="Microsoft 365 (OAuth 2.0)",
    summary=(
        "Sends from a CER mailbox in Exchange Online using an app registration. "
        "CER's mail domain is hosted by Microsoft 365."
    ),
    who="The Microsoft 365 / Entra ID administrator at CER.",
    recommended=True,
    steps=(
        GuideStep("In the Entra admin center, open App registrations and choose New registration. Allow accounts in this organizational directory only."),
        GuideStep("Open API permissions › Add a permission › APIs my organization uses › Office 365 Exchange Online › Application permissions, and add SMTP.SendAsApp."),
        GuideStep("Choose Grant admin consent for the directory."),
        GuideStep("Open Certificates & secrets › New client secret. Copy the Value column — not the Secret ID. It is shown only once. Note its expiry date."),
        GuideStep("In Exchange Online PowerShell, register the app: New-ServicePrincipal -AppId <Application (client) ID> -ObjectId <Object ID>. Use the Object ID from Enterprise applications, not from App registrations."),
        GuideStep("Grant the app access to the sender mailbox: Add-MailboxPermission -Identity <sender mailbox> -User <service principal> -AccessRights FullAccess."),
        GuideStep("Make sure the sender mailbox has an Exchange Online license and SMTP AUTH enabled in the Exchange admin center."),
    ),
    fields=(
        ProviderField("tenant_id", "Directory (tenant) ID", FieldKind.PUBLIC_IDENTIFIER,
                      source="Entra admin center › Overview", format="GUID", pattern=GUID),
        ProviderField("client_id", "Application (client) ID", FieldKind.PUBLIC_IDENTIFIER,
                      source="App registrations › your app › Overview", format="GUID", pattern=GUID),
        ProviderField("client_secret", "Client secret", FieldKind.SECRET,
                      source="Certificates & secrets › New client secret › Value",
                      format="Copy the Value, not the Secret ID", expires=True),
        ProviderField("sender", "Sender mailbox", FieldKind.MAILBOX,
                      source="The licensed mailbox from step 6", format="name@example.com",
                      pattern=EMAIL),
        ProviderField("smtp_host", "SMTP host", FieldKind.PRESET, source="Microsoft 365",
                      default="smtp.office365.com", pattern=HOSTNAME),
        ProviderField("smtp_port", "SMTP port", FieldKind.PRESET, source="Microsoft 365 (STARTTLS)",
                      default=587, pattern=PORT),
    ),
    warnings=(
        "Microsoft disables basic authentication for SMTP AUTH by default at the end of December 2026. "
        "OAuth is the configuration that keeps working.",
    ),
    docs=(
        DocLink("Authenticate SMTP with OAuth (Microsoft Learn)",
                "https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth"),
        DocLink("Basic auth retirement for SMTP AUTH (Microsoft)",
                "https://techcommunity.microsoft.com/blog/exchange/exchange-online-to-retire-basic-auth-for-client-submission-smtp-auth/4114750"),
    ),
)

_SMTP_BASIC = Provider(
    key="smtp_basic",
    title="SMTP with username and password",
    summary=(
        "Any SMTP relay that accepts a username and password: SendGrid, Amazon SES, "
        "Mailgun, or Microsoft 365 while basic authentication lasts."
    ),
    who="Whoever administers the chosen email service.",
    steps=(
        GuideStep("In your email service, create SMTP credentials dedicated to this application."),
        GuideStep("Note the SMTP host and port the service documents for STARTTLS (usually 587)."),
        GuideStep("Verify the sender address or domain in the service, or messages will be rejected."),
    ),
    fields=(
        ProviderField("host", "SMTP host", FieldKind.ENDPOINT, source="Your email service's SMTP settings",
                      format="smtp.example.com", pattern=HOSTNAME),
        ProviderField("port", "SMTP port", FieldKind.ENDPOINT, source="Your email service's SMTP settings",
                      format="587", default=587, pattern=PORT),
        ProviderField("use_tls", "Use STARTTLS", FieldKind.CHOICE, source="Your email service's SMTP settings",
                      default="true", choices=("true", "false")),
        ProviderField("username", "SMTP username", FieldKind.PUBLIC_IDENTIFIER,
                      source="The SMTP credentials you created"),
        ProviderField("password", "SMTP password", FieldKind.SECRET,
                      source="The SMTP credentials you created"),
        ProviderField("sender", "Sender address", FieldKind.MAILBOX,
                      source="A verified sender in your email service", pattern=EMAIL),
    ),
    warnings=(
        "For Microsoft 365 this configuration stops working when Microsoft disables basic authentication. Prefer OAuth.",
    ),
)

# ══ Almacén de evidencia ═══════════════════════════════════════════════════

_S3 = Provider(
    key="s3_compatible",
    title="DigitalOcean Spaces or another S3-compatible store",
    summary=(
        "Stores uploaded evidence in object storage. Works with DigitalOcean Spaces, "
        "where the application is deployed, and with AWS S3."
    ),
    who="The owner of the DigitalOcean account.",
    recommended=True,
    steps=(
        GuideStep("In the DigitalOcean control panel, open Spaces Object Storage and create a bucket. Keep it private and without CDN."),
        GuideStep("Open the Access Keys tab and choose Create Access Key."),
        GuideStep("Choose Limited Access, select only this bucket, and grant Read/Write/Delete."),
        GuideStep("Copy the Access Key ID and the Secret Key. The secret cannot be retrieved later."),
    ),
    fields=(
        ProviderField("endpoint", "Endpoint", FieldKind.ENDPOINT, source="Spaces › your bucket › Settings",
                      format="https://nyc3.digitaloceanspaces.com", pattern=HTTPS_URL),
        ProviderField("region", "Region", FieldKind.CHOICE, source="The region of your bucket",
                      format="nyc3"),
        ProviderField("bucket", "Bucket", FieldKind.PUBLIC_IDENTIFIER, source="The bucket name",
                      format="lowercase letters, digits, dots and hyphens", pattern=BUCKET),
        ProviderField("access_key_id", "Access key ID", FieldKind.PUBLIC_IDENTIFIER,
                      source="Spaces › Access Keys"),
        ProviderField("secret_access_key", "Secret access key", FieldKind.SECRET,
                      source="Spaces › Access Keys (shown once)"),
        ProviderField("prefix", "Key prefix", FieldKind.POLICY, source="Chosen by CER",
                      format="evidence/", default="evidence/", required=False),
    ),
    docs=(
        DocLink("Manage access to Spaces (DigitalOcean)",
                "https://docs.digitalocean.com/products/spaces/how-to/manage-access/"),
    ),
)

_LOCAL = Provider(
    key="local",
    title="Local filesystem",
    summary="Stores evidence on the application server's disk. For development only.",
    who="Nobody: no credentials.",
    steps=(GuideStep("No setup. Files are written under the configured root."),),
    fields=(
        ProviderField("root", "Storage root", FieldKind.ENDPOINT, source="The application server",
                      format="./var", default="", required=False),
    ),
    warnings=(
        "Files live on one server's disk. With more than one application instance, each sees different documents. Not for production.",
    ),
)

# ══ Escáner de malware ══════════════════════════════════════════════════════

_CLAMAV = Provider(
    key="clamav",
    title="ClamAV (self-hosted)",
    summary=(
        "Open-source scanner running inside CER's own infrastructure. Uploaded "
        "documents never leave it — recommended for PII and other sensitive files."
    ),
    who="Whoever deploys the application on DigitalOcean App Platform.",
    recommended=True,
    steps=(
        GuideStep("Add a service component to the App Platform app using the official clamav/clamav image."),
        GuideStep("Expose port 3310 as an internal port only (internal_ports: [3310]); it must not be public."),
        GuideStep("Use the component's name as the host below: components reach each other by name inside the app."),
    ),
    fields=(
        ProviderField("host", "Host", FieldKind.ENDPOINT, source="The internal service name in App Platform",
                      format="clamav", pattern=HOSTNAME),
        ProviderField("port", "Port", FieldKind.ENDPOINT, source="The service's internal port",
                      default=3310, pattern=PORT),
        ProviderField("timeout_seconds", "Timeout (seconds)", FieldKind.POLICY, source="Chosen by CER",
                      default=30, pattern=r"^[0-9]{1,3}$"),
    ),
    docs=(
        DocLink("Internal routing in App Platform (DigitalOcean)",
                "https://docs.digitalocean.com/products/app-platform/how-to/manage-internal-routing/"),
    ),
)

_CLOUDMERSIVE = Provider(
    key="cloudmersive",
    title="Cloudmersive Virus Scan API",
    summary="Hosted scanning API. Documents are sent to Cloudmersive for each scan.",
    who="Whoever holds CER's Cloudmersive account.",
    steps=(
        GuideStep("Sign in to the Cloudmersive portal and open API Keys."),
        GuideStep("Create a key for this application and copy it."),
        GuideStep("Review and sign Cloudmersive's Data Processing Agreement before sending documents with personal data."),
    ),
    fields=(
        ProviderField("api_key", "API key", FieldKind.SECRET, source="Cloudmersive portal › API Keys"),
        ProviderField("endpoint", "API endpoint", FieldKind.PRESET, source="Cloudmersive",
                      default="https://api.cloudmersive.com", pattern=HTTPS_URL),
    ),
    warnings=(
        "Every uploaded document is sent to a third party. Decide whether that is acceptable before enabling it.",
    ),
    docs=(
        DocLink("Stateless processing (Cloudmersive)",
                "https://cloudmersive.com/knowledge-base/Stateless-Processing-of-Cloud-Storage-Keys-in-Virus-Scanning-API"),
    ),
)


# ── Routing vial (RTE06) ────────────────────────────────────────────────────
#
# Los dos primeros son auto-alojados y no llevan credencial: por eso su URL
# vive en `ROUTE_ROUTING_URL` sin cifrar. El tercero es comercial y **sí** la
# lleva, así que su clave va por la ranura cifrada como cualquier otra.

_OSRM = Provider(
    key="osrm",
    title="OSRM (self-hosted)",
    summary="Open Source Routing Machine on CER's own infrastructure. No credential, no per-request cost.",
    who="Whoever administers CER's infrastructure.",
    recommended=True,
    steps=(
        GuideStep("Download an OSM extract that covers the operating area.",
                  "https://download.geofabrik.de/"),
        GuideStep("Preprocess it with osrm-extract, osrm-partition and osrm-customize."),
        GuideStep("Serve it with osrm-routed --algorithm mld, reachable only from the application."),
        GuideStep("Set ROUTE_ROUTING_URL to its base URL and restart the application."),
    ),
    fields=(
        ProviderField("base_url", "Base URL", FieldKind.ENDPOINT,
                      source="The OSRM instance", format="http://host:5000"),
    ),
    warnings=(
        "OSRM has no authentication. Keep it on a private network and never expose it to the internet.",
        "The extract must cover the operating area: outside it the engine answers NoSegment, which is the truthful answer.",
    ),
    docs=(DocLink("OSRM backend", "https://github.com/Project-OSRM/osrm-backend"),),
)

_VALHALLA = Provider(
    key="valhalla",
    title="Valhalla (self-hosted)",
    summary="A second self-hosted engine, different implementation, same OSM data. Used as the fallback.",
    who="Whoever administers CER's infrastructure.",
    steps=(
        GuideStep("Build the tiles from the same OSM extract."),
        GuideStep("Serve it and set ROUTE_ROUTING_FALLBACK_URL."),
    ),
    fields=(
        ProviderField("base_url", "Base URL", FieldKind.ENDPOINT,
                      source="The Valhalla instance", format="http://host:8002"),
    ),
    warnings=(
        "A different engine covers a defect in the other one; a second OSRM would not.",
    ),
    docs=(DocLink("Valhalla", "https://github.com/valhalla/valhalla"),),
)

_TOMTOM = Provider(
    key="tomtom",
    title="TomTom Routing API",
    summary="Hosted routing API. Every pair of waypoints is sent to TomTom, and each segment costs a request.",
    who="Whoever holds CER's TomTom Developer account.",
    steps=(
        GuideStep("Sign in to the TomTom Developer Portal and create an API key.",
                  "https://developer.tomtom.com/"),
        GuideStep("Restrict the key to the Routing API and to CER's egress addresses."),
        GuideStep("Store the key here. It is encrypted with the platform master key."),
        GuideStep("Confirm with TomTom that the licence allows storing the derived distance permanently (see the warning below)."),
    ),
    fields=(
        ProviderField("api_key", "API key", FieldKind.SECRET,
                      source="TomTom Developer Portal > Dashboard > Keys"),
        ProviderField("base_url", "API endpoint", FieldKind.PRESET, source="TomTom",
                      default="https://api.tomtom.com", pattern=HTTPS_URL),
    ),
    warnings=(
        "RTE06 section 27 and 28 require every segment distance to be kept and auditable forever. "
        "Confirm TomTom's terms allow permanent storage of derived routing content before enabling this "
        "with real data: it is a contractual check, not a technical one.",
        "Supervisor coordinates leave CER's infrastructure on every segment.",
        "Traffic-aware routing is disabled on purpose so the same waypoints always return the same distance. "
        "Without that, a mileage fact could not be reproduced later.",
    ),
    docs=(DocLink("Calculate Route (TomTom)",
                  "https://developer.tomtom.com/routing-api/documentation/routing/calculate-route"),),
)


INTEGRATIONS: tuple[Integration, ...] = (
    Integration(
        key="email",
        title="Outbound email",
        summary="Password resets and notifications travel through it.",
        required=True,
        providers=(_M365, _SMTP_BASIC),
        capability_key="email",
    ),
    Integration(
        key="email_fallback",
        title="Outbound email — fallback provider",
        summary=(
            "A second, independent email provider. Sending tries the provider above first; "
            "if it is not configured or fails, this one is used instead. Both can be configured "
            "at the same time — CER's fallback policy: never let a missing credential stop a flow "
            "that has a working alternative."
        ),
        required=False,
        providers=(_M365, _SMTP_BASIC),
        capability_key="email_fallback",
    ),
    Integration(
        key="document_storage",
        title="Document storage",
        summary="Where uploaded files are kept.",
        required=True,
        providers=(_S3, _LOCAL),
        capability_key="document_storage",
    ),
    Integration(
        key="malware_scanner",
        title="Malware scanning",
        summary="Inspects every uploaded document before it can be viewed.",
        required=True,
        providers=(_CLAMAV, _CLOUDMERSIVE),
        open_decision="OD-08",
        capability_key="malware_scanner",
    ),
    Integration(
        key="road_routing",
        title="Road routing engine",
        summary=(
            "Turns the captured waypoints of a trip into its official mileage. Without it "
            "the mileage stays pending and then terminalises saying so: it never invents a number."
        ),
        required=False,
        providers=(_OSRM, _VALHALLA, _TOMTOM),
        capability_key="road_routing",
    ),
)

BY_KEY: dict[str, Integration] = {i.key: i for i in INTEGRATIONS}


def validate_config(provider: Provider, config: dict) -> tuple[dict, list[str]]:
    """Normaliza la configuración no secreta y devuelve los errores.

    Un campo secreto enviado aquí es un error: los secretos van por su propio
    endpoint, que los cifra. Aceptarlo en `config` lo guardaría en claro.
    """
    errores: list[str] = []
    limpio: dict[str, str | int | bool] = {}

    for nombre in config:
        campo = provider.field(nombre)
        if campo is None:
            errores.append(f"'{nombre}' is not a field of {provider.title}.")
        elif campo.secret:
            errores.append(f"'{nombre}' is a secret; set it through the secrets endpoint.")

    for campo in provider.config_fields:
        valor = config.get(campo.name, campo.default)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            if campo.required:
                errores.append(f"{campo.label} is required.")
            continue
        texto = str(valor).strip()
        if campo.choices and texto not in campo.choices:
            errores.append(f"{campo.label} must be one of: {', '.join(campo.choices)}.")
            continue
        if campo.pattern and not re.fullmatch(campo.pattern, texto):
            errores.append(f"{campo.label} does not look like {campo.format or 'a valid value'}.")
            continue
        limpio[campo.name] = int(texto) if campo.pattern in (PORT,) or campo.name.endswith("_seconds") else texto

    return limpio, errores


@dataclass
class IntegrationReadiness:
    status: str
    missing: list[str] = field(default_factory=list)


def assess(
    integration: Integration,
    *,
    provider_key: str | None,
    enabled: bool,
    config: dict,
    secret_names: set[str],
    verified: bool,
    master_key_ok: bool,
    failing: bool = False,
) -> IntegrationReadiness:
    """En qué punto está una integración. Lo que Settings pinta en su tarjeta.

    `verified` sólo cuenta si nada cambió después: quien guarda la integración
    borra la verificación, así que llega aquí ya resuelto.
    """
    provider = integration.provider(provider_key)
    if provider is None:
        return IntegrationReadiness("not_configured", ["Choose a provider."])
    if not provider.available:
        return IntegrationReadiness("unavailable", ["Requires a connector built to USCIS's ICA."])
    if not enabled:
        return IntegrationReadiness("disabled")

    _, errores = validate_config(provider, config)
    faltan = errores + [
        f"{f.label} is not set." for f in provider.secret_fields if f.required and f.name not in secret_names
    ]
    if faltan:
        return IntegrationReadiness("incomplete", faltan)
    if provider.secret_fields and not master_key_ok:
        return IntegrationReadiness("master_key_missing", ["PLATFORM_MASTER_KEY is not configured or does not match."])
    if failing:
        return IntegrationReadiness("failing", ["The last check failed. See Diagnostics."])
    if not verified:
        return IntegrationReadiness("configured", ["Run Verify to confirm it works."])
    return IntegrationReadiness("verified")
