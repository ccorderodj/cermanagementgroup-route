/**
 * Tipos globales de la aplicación.
 *
 * Este archivo tenía 302 líneas, de las cuales ~200 eran ejercicios de un curso
 * de TypeScript (`ArtFeaturesGlobal`, `paintDarkSiennaCabin`, `printFruitCatalog`,
 * `DataSDKGlobal`, `KeyFilteredDocGlobal`...) con enlaces a typescript-training.com.
 * Los tipos que el proyecto sí usa estaban enterrados entre ellos (AUD-FE-018).
 * Se conserva únicamente lo que tiene consumidores reales.
 */

// ── Utilidades ──────────────────────────────────────────────────────────────

type DeepPartial<T> = T extends object ? { [P in keyof T]?: DeepPartial<T[P]> } : T;

type OptionalRecord<K extends keyof any, T> = { [P in K]?: T };

type RequireOnly<T, P extends keyof T> = Pick<T, P> & Partial<Omit<T, P>>;

// ── Sesión y tenant ─────────────────────────────────────────────────────────

/**
 * Contenido de la cookie `user_data`.
 *
 * Son **pistas para la interfaz**, no autorización. La cookie es legible y
 * editable desde el navegador; el backend recalcula los permisos contra la base
 * en cada petición. Ocultar un botón aquí mejora la experiencia, no la
 * seguridad.
 */
interface UserLogged {
    user_id: number;
    first_name: string;
    last_name: string;
    username: string;
    email: string;
    gender: boolean;
    groups: string[];
    permissions: string[];
    /** Privilegio de plataforma. Informativo: no se puede conceder desde el tenant. */
    is_superuser: boolean;
}

/** Contenido de la cookie `app_data`: identidad visual del tenant. */
interface AppData {
    // Identidad del proyecto (settings APP_* en el servidor).
    app_name: string;
    app_title: string;
    brand_label: string;
    brand_tagline: string;
    logo_path: string;
    icon_path: string;
    /** Banda de entorno; vacía = no se muestra. */
    environment_label: string;
    /** Página a la que se entra tras iniciar sesión. */
    default_path: string;

    mode: 'DEV' | 'TEST' | 'PROD';
    company_id: number;
    company_name: string;
    subdomain: string;
    address?: string | null;
    email?: string | null;
    phone_secondary?: string | null;
    website?: string | null;
    logo_url?: string | null;
    brand_primary_color?: string | null;
    brand_secondary_color?: string | null;
    pdf_text_color?: string | null;
    pdf_muted_text_color?: string | null;
    pdf_surface_color?: string | null;
}

// ── Estado y paginación ─────────────────────────────────────────────────────

interface GlobalsCommonSchema {
    isLoading: boolean;
    error?: string;
}

/**
 * Lo que **devuelve** el backend en un endpoint paginado.
 *
 * `page_size` NO está aquí a propósito: el backend no lo envía. El tipo
 * anterior lo declaraba obligatorio, así que cualquier lectura obtenía
 * `undefined` con tipo `number` y TypeScript no podía avisar (AUD-FE-010).
 */
interface IResultPagination<T> {
    count: number;
    next: string | null;
    previous: string | null;
    results: T[];
}

/**
 * Lo que **guarda el slice**: la respuesta del servidor más el estado de la
 * tabla en el cliente.
 *
 * `index_page` es base 0 porque así lo maneja TanStack Table; el backend usa
 * base 1. La traducción está en `shared/lib/store/pagination.ts`, en un único
 * sitio en vez de copiada en cada thunk (AUD-FE-012).
 */
interface IPaginationState<T> extends IResultPagination<T> {
    page_size: number;
    index_page: number;
}

interface IEntitySchema<T> extends GlobalsCommonSchema {
    data: T[];
}

// ── Módulos sin tipos propios ───────────────────────────────────────────────

declare module '*.scss' {
    interface IClassNames {
        [className: string]: string;
    }
    const classNames: IClassNames;
    export = classNames;
}

declare module '*.svg';
declare module '*.jpg';
declare module '*.jpeg';
declare module '*.png';

declare const __IS_DEV__: boolean;
declare const __API__: string;
declare const __PROJECT__: 'storybook' | 'frontend' | 'jest';
