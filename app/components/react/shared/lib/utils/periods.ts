/**
 * Vocabulario de períodos para filtros de fecha.
 *
 * Vivía en `features/Reports` (dominio de inventario, ya eliminado), pero es
 * genérico y lo consume `calculateDateRange` en `utils.ts`, así que su sitio
 * es `shared/lib/utils` según la regla 8 de AGENTS.md.
 */
export enum PeriodLabels {
    CustomDates = 'Custom Dates',
    CurrentWeek = 'Current Week',
    LastWeek = 'Last Week',
    CurrentMonth = 'Current Month',
    LastMonth = 'Last Month',
    CurrentYear = 'Current Year',
    LastYear = 'Last Year',
    CurrentQuarter = 'Current Quarter',
    LastQuarter = 'Last Quarter',
    CurrentHalfYear = 'Current Half Year',
    LastHalfYear = 'Last Half Year',
}
