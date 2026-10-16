/** Un estado donde opera la compañía, con su marca de sede principal. */
export interface OperatingState {
    id: number;
    code: string;
    name: string;
    is_main: boolean;
    is_active: boolean;
    created_at?: string | null;
    updated_at?: string | null;
}

/** Un estado del catálogo de EE.UU., marcando si la compañía opera en él. */
export interface OperatingStateCatalogItem {
    id: number;
    code: string;
    name: string;
    enabled: boolean;
}

export interface Region {
    id: number;
    name: string;
}

export interface RegionsSchema extends GlobalsCommonSchema {
    data: Region[];
    region_ids?: number[]
    regionId?: number;
}

/**
 * Lo que guarda el slice: la respuesta del servidor mas el estado de la tabla
 * en el cliente (`page_size`, `index_page`). El envoltorio que devuelve la API
 * es `IResultPagination`, que NO trae `page_size` porque el backend no lo envia
 * (AUD-FE-010).
 */
export interface RegionsPaginationResult extends IPaginationState<Region> {}

export interface RegionSchema extends GlobalsCommonSchema {
    data: Region | undefined;
}

export interface RegionsPaginationSchema extends GlobalsCommonSchema {
    data: RegionsPaginationResult;
}
