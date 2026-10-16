import {
    memo,
    useEffect,
    useState,
} from 'react';
import { useSelector } from 'react-redux';

import { useAppDispatch } from '@/shared/lib/hooks/useAppDispatch/useAppDispatch';
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from '@/shared/ui/shadcn/new-york/Popover/Popover';
import { Button } from '@/shared/ui/shadcn/new-york/Button/Button';
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from '@/shared/ui/shadcn/new-york/Command/Command';

import {
    getRegionsData,
    getRegionsError,
    getRegionsIsLoading,
    Region,
    fetchRegions,
    regionsSliceActions,
} from '../..';
import { cn } from '@/shared/lib/utils/utils';

export const RegionFilterDropDown = memo(() => {
    const dispatch = useAppDispatch();
    const regions = useSelector(getRegionsData);
    const isLoading = useSelector(getRegionsIsLoading);
    const error = useSelector(getRegionsError);

    const [open, setOpen] = useState(false);
    const [selectedRegion, setSelectedRegion] = useState<Region | null>(null);

    useEffect(() => {
        dispatch(fetchRegions());
    }, [dispatch]);

    useEffect(() => {
        // dispatch(fetchCompanies());
        if (selectedRegion?.id) {
            dispatch(regionsSliceActions.setRegionId(selectedRegion.id));
        }
    }, [dispatch, selectedRegion]);

    if (error) {
        return (
            <span className="text-destructive">
                Failed to load Regions
            </span>
        );
    }

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    className="w-full justify-between text-left font-normal"
                    disabled={isLoading}
                >
                    {selectedRegion ? selectedRegion.name : 'Select Region'}
                </Button>
            </PopoverTrigger>

            <PopoverContent className="p-0 w-[280px]" align="start">
                <Command>
                    <CommandInput placeholder="Search regions..." />

                    <CommandList>
                        <CommandEmpty>No results found.</CommandEmpty>

                        <CommandGroup>
                            {regions.map((region) => {
                                const isSelected = selectedRegion?.id === region.id;

                                return (
                                    <CommandItem
                                        key={region.id}
                                        value={region.name}
                                        onSelect={() => {
                                            setSelectedRegion(region);
                                            setOpen(false);
                                        }}
                                        className={cn(
                                            'cursor-pointer',
                                            isSelected && 'bg-primary/10 text-primary font-medium',
                                        )}
                                    >
                                        <span className="flex-1">{region.name}</span>

                                        {isSelected && <span className="ml-2">✓</span>}
                                    </CommandItem>
                                );
                            })}
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    );
});
