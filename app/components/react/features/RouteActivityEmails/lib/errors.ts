/**
 * Lo que devuelve el servidor al rechazar un guardado, ya repartido.
 *
 * `422` trae errores por campo (`loc: ['body', 'subject' | 'body']`); `409` es
 * que otra persona cambió lo mismo, o que la persona no es elegible; lo demás
 * es un mensaje general.
 */
export interface ServerProblem {
    status: number | null;
    fields: Partial<Record<'subject' | 'body', string>>;
    message: string | null;
}

interface ErrorWithResponse {
    response?: { status?: number; data?: { detail?: unknown } };
}

export function readServerProblem(error: unknown, fallback: string): ServerProblem {
    const response = (error as ErrorWithResponse)?.response;
    const status = response?.status ?? null;
    const detail = response?.data?.detail;
    const fields: ServerProblem['fields'] = {};

    if (Array.isArray(detail)) {
        detail.forEach((item: { loc?: unknown[]; msg?: string }) => {
            const field = item?.loc?.[item.loc.length - 1];
            if ((field === 'subject' || field === 'body') && item.msg) {
                fields[field] = fields[field] ? `${fields[field]} ${item.msg}` : item.msg;
            }
        });
        const resto = Object.keys(fields).length ? null : fallback;
        return { status, fields, message: resto };
    }
    return { status, fields, message: typeof detail === 'string' ? detail : fallback };
}
