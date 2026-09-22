// classNames('remove-btn', { hovered: true, selectable: true, red: true}, ['pdg'])
// remove-btn hovered selectable pdg
export type Mods = Record<string, boolean | string | undefined>

export function classNames(
    cls: string,
    mods: Mods = {},
    additional: Array<string | undefined> = [],
): string {
    return [
        cls,
        ...additional.filter(Boolean),
        ...Object.entries(mods)
            .filter(([_, value]) => Boolean(value))
            .map(([className]) => className),
    ].join(' ');
}
