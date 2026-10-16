import type { ReactNode, Row, Table } from '@tanstack/react-table';

/**
 * Tipado del `meta` de TanStack Table.
 *
 * TanStack declara `TableMeta` como una interfaz vacía a propósito, para que
 * cada aplicación la amplíe con lo que necesite. Sin esto, el patrón de
 * acciones de fila que usa el proyecto (regla 11 de AGENTS.md) llega al
 * componente como `any` implícito.
 */
declare module '@tanstack/react-table' {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    interface TableMeta<TData extends unknown> {
        renderRowActions?: (args: {
            row: Row<TData>;
            table: Table<TData>;
        }) => ReactNode;
    }
}
