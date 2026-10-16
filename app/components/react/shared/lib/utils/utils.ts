import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { AxiosError } from 'axios';
import {
    eachMonthOfInterval,
    endOfMonth,
    endOfWeek,
    format,
    parseISO,
    startOfWeek,
    subMonths,
    subQuarters,
    subWeeks,
    subYears,
} from 'date-fns';
import { enUS, es, fr } from 'date-fns/locale';
import { PeriodLabels } from './periods';

export const DATE_FORMAT = 'MM-dd-yyyy';
export const YYYY_MM = 'yyyy-MM';
export const YYYYMMDD_FORMAT = 'yyyy-MM-dd';
export const DATE_FORMAT_ISO = YYYYMMDD_FORMAT;

export const getSafeDateString = (value: Date | string): string => {
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
        return format(value, 'yyyy-MM-dd');
    }

    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
        return format(parsed, 'yyyy-MM-dd');
    }

    return String(value).replace(/[^0-9A-Za-z_-]/g, '-');
};

export enum TaxesEnum {
    W9 = 'W9',
    W2 = 'W2',
}

export enum YesNoEnum {
    Yes = 'Yes',
    No = 'No',
}

export enum MaritalStatusEnum {
    Single = 'Single',
    Married = 'Married',
    Divorced = 'Divorced',
    Widowed = 'Widowed',
}

export const getMonthsInRangeDate = (startDate: string, endDate: string) => {
    const start = parseISO(startDate);
    const end = parseISO(endDate);

    const months = eachMonthOfInterval({ start, end });

    // Format each month in 'yyyy-MM' format
    return months.map((month) => format(month, YYYY_MM));
};

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export const normalizeSpaces = (input: string) => {
    return input.trim().replace(/\s+/g, ' ');
};

export function createQueryString(params: Record<string, string | number | boolean | undefined | null>): string {
    const queryString = Object.entries(params)
        .filter(([_, value]) => value !== undefined && value !== null)
        .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`)
        .join('&');
    return queryString ? `?${queryString}` : '';
}

// Utility to remove undefined or null values from an object
export function cleanPayload<T extends object>(payload: T): Partial<T> {
    return Object.fromEntries(
        Object.entries(payload as Record<string, unknown>)
            .filter(([_, value]) => value !== undefined && value !== null && value !== ''),
    ) as Partial<T>;
}

export const handleAsyncError = (error: AxiosError, rejectWithValue: Function) => {
    if (error.response) {
        if (error.response.status === 422) {
            const errorMessages = error.response.data;
            return rejectWithValue(errorMessages);
        }

        if (error.response.status === 401) {
            const errorMessages = error.response.data;
            return rejectWithValue(errorMessages);
        }

        // If it's an HTTP error, check for DRF bad request (400) response
        if (error.response.status === 400
            || error.response.status === 403
            || error.response.status === 404
            || error.response.status === 409) { // 409 Conflict
            // Extract validation errors from DRF response
            const errorMessages = error.response.data;
            return rejectWithValue(errorMessages);
        }

        return rejectWithValue(`Request failed with status ${error.response.status}`);
    } if (error.request) {
        // If the request was made but no response was received
        return rejectWithValue('No response received from the server');
    }
    // If something else caused the error
    return rejectWithValue('Unexpected error occurred');
};

export function extractErrorMessage(
    result: any,
    defaultErrorMessage: string = 'An unknown error occurred',
): string {
    // debugger;
    const detail = result?.payload?.detail ?? result?.detail;

    if (typeof detail === 'string') {
        return detail;
    }

    if (Array.isArray(detail)) {
        // for (const error of detail) {
        //     if (typeof error === 'object' && error?.ctx?.reason) {
        //         return error.ctx.reason;
        //     }
        // }
        const errorWithReason = detail.find(
            (error) => typeof error === 'object' && error?.ctx?.reason,
        );
        if (errorWithReason) {
            return errorWithReason.ctx.reason;
        }
    }

    return defaultErrorMessage;
}

export function getFilenameFromContentDisposition(cd?: string | null, fallback = 'download.zip') {
    if (!cd) return fallback;
    // e.g. attachment; filename="something.zip"
    const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(cd);
    if (match?.[1]) {
        try { return decodeURIComponent(match[1].replace(/"/g, '')); } catch { return match[1]; }
    }
    return fallback;
}

export const calculateDateRange = (periodOptionLabel: PeriodLabels) => {
    const today = new Date();
    let startDate: Date | undefined;
    let endDate: Date | undefined;

    switch (periodOptionLabel) {
    case PeriodLabels.CurrentWeek:
    case PeriodLabels.LastWeek: {
        // Determine if we need current week or last week
        const isLastWeek = periodOptionLabel === PeriodLabels.LastWeek;
        const weekDate = isLastWeek ? subWeeks(today, 1) : today;

        // Get the start and end of the week based on the determined date
        startDate = startOfWeek(weekDate, { weekStartsOn: 1 });
        endDate = endOfWeek(weekDate, { weekStartsOn: 1 });
        break;
    }

    case PeriodLabels.CurrentMonth:
    case PeriodLabels.LastMonth: {
        // Determine if we need current month or last month
        const isLastMonth = periodOptionLabel === PeriodLabels.LastMonth;
        const monthDate = isLastMonth ? subMonths(today, 1) : today;

        // Get the start and end of the month
        startDate = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
        endDate = endOfMonth(monthDate);
        break;
    }

    case PeriodLabels.CurrentYear:
    case PeriodLabels.LastYear: {
        // Determine if we need current year or last year
        const isLastYear = periodOptionLabel === PeriodLabels.LastYear;
        const yearDate = isLastYear ? subYears(today, 1) : today;

        // Get the start and end of the year
        startDate = new Date(yearDate.getFullYear(), 0, 1);
        endDate = new Date(yearDate.getFullYear(), 11, 31);
        break;
    }

    case PeriodLabels.CurrentQuarter:
    case PeriodLabels.LastQuarter: {
        // Determine if we need current quarter or last quarter
        const isLastQuarter = periodOptionLabel === PeriodLabels.LastQuarter;
        const quarterDate = isLastQuarter ? subQuarters(today, 1) : today;

        // Get the start and end of the quarter
        const currentQuarter = Math.floor((quarterDate.getMonth() + 3) / 3);
        const quarterStartMonth = (currentQuarter - 1) * 3;
        const quarterEndMonth = quarterStartMonth + 2;

        startDate = new Date(quarterDate.getFullYear(), quarterStartMonth, 1);
        endDate = new Date(quarterDate.getFullYear(), quarterEndMonth + 1, 0);
        break;
    }

    case PeriodLabels.CurrentHalfYear:
    case PeriodLabels.LastHalfYear: {
        const isLastHalfYear = periodOptionLabel === PeriodLabels.LastHalfYear;
        const referenceDate = isLastHalfYear ? subMonths(today, 6) : today;
        const month = referenceDate.getMonth();
        const year = referenceDate.getFullYear();

        const isFirstHalf = month < 6;

        if (isFirstHalf) {
            startDate = new Date(year, 0, 1); // Jan 1
            endDate = new Date(year, 5, 30); // Jun 30
        } else {
            startDate = new Date(year, 6, 1); // Jul 1
            endDate = new Date(year, 11, 31); // Dec 31
        }
        break;
    }

    default:
        return {
            startDate: undefined,
            endDate: undefined,
        };
    }

    return { startDate, endDate };
};

export const getDateLocale = (lang: string) => {
    switch (lang) {
    case 'es':
        return es;
    case 'ht':
        return fr; // or enUS if you prefer English month names for Creole
    default:
        return enUS;
    }
};

export function formatIsoDate(iso?: string | null): string {
    if (!iso) return '-';

    const [y, m, d] = iso.split('-').map(Number);
    if (!y || !m || !d) return iso;

    const date = new Date(y, m - 1, d);
    return Number.isNaN(date.getTime()) ? iso : date.toLocaleDateString();
}

export function parseIsoDateAsLocal(value?: string | null): Date | null {
    if (!value) return null;

    const [y, m, d] = value.split('-').map(Number);
    if (!y || !m || !d) return null;

    return new Date(y, m - 1, d);
}

export function formatIsoDateLabel(value?: string | null): string {
    const parsedDate = parseIsoDateAsLocal(value);
    if (!parsedDate) {
        return value || '';
    }
    return format(parsedDate, YYYYMMDD_FORMAT);
}

export function normalizeIdentifierToken(value: string): string {
    return value
        .trim()
        .toUpperCase()
        .replace(/\s+/g, '') // remove spaces
        .replace(/[^A-Z0-9]/g, ''); // keep alphanumeric only
}

export function buildNameFromParts(...parts: string[]): string {
    return parts
        .map((p) => p?.trim())
        .filter(Boolean)
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim();
}

export function buildIdentifierFromParts(
    parts: string[],
    separator = '_',
): string {
    const normalized = parts
        .map((p) => normalizeIdentifierToken(p))
        .filter(Boolean);

    if (!normalized.length) return '';

    return normalized.join(separator);
}

export const isValidTwoDigitIntString = (value: string) => {
    if (value === '') return true;
    return /^(?:\d{1,2})$/.test(value);
};

const HEX_COLOR_REGEX = /^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$/;

export const getSafeHexColor = (
    color: string | null | undefined,
    fallback: string,
): string => {
    if (!color) return fallback;
    return HEX_COLOR_REGEX.test(color) ? color : fallback;
};

// Convierte un hex (#rrggbb / #rgb) al triple "H S% L%" que usan los tokens
// shadcn (`hsl(var(--primary))`); null si el valor no es un hex válido.
export const hexToHslTriple = (color: string | null | undefined): string | null => {
    if (!color || !HEX_COLOR_REGEX.test(color)) return null;

    const normalized = color.length === 4
        ? color.replace('#', '').split('').map((char) => char + char).join('')
        : color.replace('#', '');

    const r = parseInt(normalized.slice(0, 2), 16) / 255;
    const g = parseInt(normalized.slice(2, 4), 16) / 255;
    const b = parseInt(normalized.slice(4, 6), 16) / 255;

    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = (max + min) / 2;

    let h = 0;
    let s = 0;

    if (max !== min) {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);

        if (max === r) {
            h = (g - b) / d + (g < b ? 6 : 0);
        } else if (max === g) {
            h = (b - r) / d + 2;
        } else {
            h = (r - g) / d + 4;
        }
        h /= 6;
    }

    return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
};

/**
 * Parametro de la pagina impreso por el servidor en el ancla `#rc-currentPage`.
 *
 * No hay router de frontend (server-route + page-key), asi que una pagina de
 * detalle no analiza `window.location` por su cuenta: la ruta de FastAPI ya
 * conoce el identificador y la plantilla Jinja lo imprime como atributo
 * `data-*`. Leerlo aqui mantiene una sola fuente y un solo formato de URL.
 *
 *     <div id="rc-currentPage" data-current-page="..." data-client-id="7">
 *     readPageNumberParam('clientId')  // 7
 */
export function readPageNumberParam(name: string): number | null {
    if (typeof document === 'undefined') return null;

    const anchor = document.getElementById('rc-currentPage');
    const raw = anchor?.dataset?.[name];
    if (!raw) return null;

    const value = Number(raw);
    return Number.isFinite(value) && value > 0 ? value : null;
}

/**
 * Evidencia de tiempo del dispositivo para una acción encolada.
 *
 * Por qué es genérica y no de la Jornada
 * --------------------------------------
 * Toda acción que pueda esperar en la cola durable necesita decir **cuándo la
 * pulsó la persona**, no cuándo el servidor la recibió. Sin esto, una acción que
 * pasó dos horas sin cobertura se registra con la hora de recepción, y la
 * jornada o el viaje quedan fechados a una hora que no ocurrió. La Jornada
 * (RTE03) y el Viaje (RTE04) lo necesitan igual, así que vive aquí y no en una
 * de las dos: duplicarla sería dos formas de fechar el mismo día.
 *
 * El servidor no se fía de esto. Valida la evidencia contra la causalidad y el
 * orden del ciclo de vida, y si no cuadra usa su propio reloj y lo deja marcado
 * como `server_receipt`.
 */
export interface DeviceTimeEvidence {
    device_captured_at: string;
    utc_offset_minutes: number;
}

export function captureTimeEvidence(): DeviceTimeEvidence {
    return {
        device_captured_at: new Date().toISOString(),
        // `getTimezoneOffset()` devuelve minutos al OESTE de UTC; el backend
        // espera minutos al ESTE (D-10), de ahí el signo invertido.
        utc_offset_minutes: -new Date().getTimezoneOffset(),
    };
}

/**
 * La zona IANA del dispositivo (`America/New_York`), o `null` si el navegador
 * no la da.
 *
 * Sólo viaja en `Start Work` (T-1/T-2): fija la zona de la jornada, y el resto
 * de acciones no la necesitan —sus instantes son absolutos y se muestran en la
 * zona de su jornada—. Se captura al **encolar**, junto al instante, para que
 * una acción que esperó sin cobertura no tome la zona del momento de
 * sincronizar. Es configuración del equipo, no ubicación.
 */
export function deviceTimeZone(): string | null {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
    } catch {
        return null;
    }
}

/** La zona con que se registraron los instantes de una jornada. */
export interface EventTimeZone {
    /** Zona IANA efectiva de la jornada. Nula en las anteriores a T-1/T-2. */
    timeZone?: string | null;
    /** Desfase al iniciar la jornada: lo único que tienen las históricas. */
    utcOffsetMinutes?: number | null;
}

/**
 * Un instante leído en el reloj de la zona de su jornada (T-1/T-2).
 *
 * `incierta` marca el único caso sin fuente horaria fiable: ni zona IANA ni
 * desfase. Ahí la hora se lee en UTC y quien la muestra tiene que decirlo;
 * presentarla a secas sería fingir una hora local que no se conoce (FR-03).
 */
interface RelojLocal {
    /** `5:41`, sin periodo. */
    reloj: string;
    periodo: string;
    /** `YYYY-MM-DD` en la zona de la jornada. */
    dia: string;
    /** `Oct 8`. */
    fecha: string;
    incierta: boolean;
}

const RELOJ_12H: Intl.DateTimeFormatOptions = {
    hour: 'numeric', minute: '2-digit', hour12: true,
};

function leerEnZona(instante: Date, timeZone: string): Omit<RelojLocal, 'incierta'> {
    // `en-US` y `hour12` explícitos: sin ellos, un navegador en español o en
    // inglés británico escribe `17:41` y la convención deja de ser una sola.
    const partes = new Intl.DateTimeFormat('en-US', { ...RELOJ_12H, timeZone })
        .formatToParts(instante);
    const valor = (tipo: Intl.DateTimeFormatPartTypes) => (
        partes.find((p) => p.type === tipo)?.value ?? ''
    );
    return {
        reloj: `${valor('hour')}:${valor('minute')}`,
        periodo: valor('dayPeriod').toUpperCase(),
        dia: new Intl.DateTimeFormat('en-CA', {
            timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
        }).format(instante),
        fecha: new Intl.DateTimeFormat('en-US', {
            timeZone, month: 'short', day: 'numeric',
        }).format(instante),
    };
}

function relojLocal(
    iso: string | null | undefined,
    zona: EventTimeZone = {},
): RelojLocal | null {
    if (!iso) return null;
    const instante = new Date(iso);
    if (Number.isNaN(instante.getTime())) return null;

    if (zona.timeZone) {
        try {
            return { ...leerEnZona(instante, zona.timeZone), incierta: false };
        } catch {
            // Una zona que este navegador no conoce: se sigue con el desfase.
        }
    }
    // Sin zona IANA —una jornada anterior a T-1/T-2—: el desfase con que se
    // registró, aplicado como reloj fijo. No se le atribuye ninguna zona ni se
    // promete el cambio de horario que un desfase no sabe (D5).
    const desfase = zona.utcOffsetMinutes ?? null;
    const desplazado = new Date(instante.getTime() + (desfase ?? 0) * 60_000);
    return { ...leerEnZona(desplazado, 'UTC'), incierta: desfase === null };
}

/**
 * La hora de un instante **en la zona de su jornada**, no en la del navegador
 * que consulta (T-2), en 12 h con AM/PM y **sin sufijo de zona** (ajuste AM/PM
 * del PO). La zona sigue gobernando la conversión; sólo deja de imprimirse.
 *
 * `zona` es `'UTC'` únicamente cuando no hay ninguna fuente horaria —ni zona ni
 * desfase—: es la advertencia de que la hora no es local, no un sufijo.
 *
 * Con `refDate` (`YYYY-MM-DD`), si el día local del instante es otro se
 * antepone la fecha: una jornada nocturna empezada ayer no puede leerse como
 * si hubiera empezado hoy.
 */
export function eventClockParts(
    iso: string | null | undefined,
    zonaDeLaJornada?: EventTimeZone,
    refDate?: string | null,
): { hora: string; zona: string } {
    const r = relojLocal(iso, zonaDeLaJornada);
    if (!r) return { hora: '—', zona: '' };
    const prefijo = refDate && r.dia !== refDate ? `${r.fecha}, ` : '';
    return {
        hora: `${prefijo}${r.reloj} ${r.periodo}`,
        zona: r.incierta ? 'UTC' : '',
    };
}

/** `eventClockParts` en una sola cadena: `5:41 PM`. */
export function formatEventClock(
    iso: string | null | undefined,
    zonaDeLaJornada?: EventTimeZone,
    refDate?: string | null,
): string {
    const { hora, zona } = eventClockParts(iso, zonaDeLaJornada, refDate);
    return zona ? `${hora} ${zona}` : hora;
}

/** Fecha y hora, para listas que mezclan días: `Oct 8, 5:41 PM`. */
export function formatEventDateTime(
    iso: string | null | undefined,
    zonaDeLaJornada?: EventTimeZone,
): string {
    const r = relojLocal(iso, zonaDeLaJornada);
    if (!r) return '—';
    return `${r.fecha}, ${r.reloj} ${r.periodo}${r.incierta ? ' UTC' : ''}`;
}

/**
 * Un tramo entre dos instantes de la misma jornada, sin repetir lo que no
 * hace falta y sin volverse ambiguo (FR-02):
 *
 * * mismo periodo: `5:41–6:02 PM`;
 * * distinto periodo: `11:50 AM–12:10 PM`;
 * * distinto día local: `11:50 PM–12:10 AM (+1 day)`.
 *
 * Los días se comparan en la zona de la jornada, no restando horas de reloj.
 * Si falta un extremo devuelve `null` y quien llama decide qué decir —`In
 * progress` no es lo mismo que «no hubo»—.
 */
export function formatClockRange(
    desdeIso: string | null | undefined,
    hastaIso: string | null | undefined,
    zonaDeLaJornada?: EventTimeZone,
): string | null {
    const a = relojLocal(desdeIso, zonaDeLaJornada);
    const b = relojLocal(hastaIso, zonaDeLaJornada);
    if (!a || !b) return null;

    const dias = Math.round(
        (Date.parse(`${b.dia}T00:00:00Z`) - Date.parse(`${a.dia}T00:00:00Z`))
            / 86_400_000,
    );
    const incierta = a.incierta ? ' UTC' : '';
    if (dias === 0 && a.periodo === b.periodo) {
        return `${a.reloj}–${b.reloj} ${b.periodo}${incierta}`;
    }
    const salto = dias === 0 ? '' : ` (${dias > 0 ? '+' : ''}${dias} day${Math.abs(dias) === 1 ? '' : 's'})`;
    return `${a.reloj} ${a.periodo}–${b.reloj} ${b.periodo}${incierta}${salto}`;
}
