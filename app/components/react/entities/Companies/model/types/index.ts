import { z } from 'zod';

/**
 * Una compania tal y como la devuelve `GET /api/companies`.
 *
 * El esquema Zod es la fuente y el tipo sale de el con `z.infer` (D14): asi no
 * pueden desincronizarse, y si el backend cambia el contrato el fallo aparece
 * en la llamada, no tres pantallas mas alla.
 */
export const companySchema = z.object({
    id: z.number(),
    name: z.string(),
    subdomain: z.string().nullable(),
    is_active: z.boolean(),
    created_at: z.string(),
    updated_at: z.string(),
});

export type Company = z.infer<typeof companySchema>;

export interface CompanyProfile {
    id: number;
    name: string;
    domain: string | null;
    subdomain: string | null;
    address: string | null;
    phone: string | null;
    email: string | null;
    phone_secondary: string | null;
    website: string | null;
    logo_url: string | null;
    brand_primary_color: string | null;
    brand_secondary_color: string | null;
    pdf_text_color: string | null;
    pdf_muted_text_color: string | null;
    pdf_surface_color: string | null;
}

export interface CompaniesSchema extends GlobalsCommonSchema {
    data: Company[];
    companyId?: number;
}

/**
 * Lo que guarda el slice: la respuesta del servidor mas el estado de la tabla
 * en el cliente (`page_size`, `index_page`). El envoltorio que devuelve la API
 * es `IResultPagination`, que NO trae `page_size` porque el backend no lo envia
 * (AUD-FE-010).
 */
export interface CompaniesPaginationResult extends IPaginationState<Company> {}

export interface Companieschema extends GlobalsCommonSchema {
    data: Company | undefined;
}

export interface CompaniesPaginationSchema extends GlobalsCommonSchema {
    data: CompaniesPaginationResult;
}
