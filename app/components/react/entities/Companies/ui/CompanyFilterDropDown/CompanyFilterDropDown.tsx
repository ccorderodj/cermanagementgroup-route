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
    getCompaniesData,
    getCompaniesError,
    getCompaniesIsLoading,
    Company,
    fetchCompanies,
    companiesSliceActions,
} from '../..';
import { cn } from '@/shared/lib/utils/utils';

export const CompanyFilterDropDown = memo(() => {
    const dispatch = useAppDispatch();
    const companies = useSelector(getCompaniesData);
    const isLoading = useSelector(getCompaniesIsLoading);
    const error = useSelector(getCompaniesError);

    const [open, setOpen] = useState(false);
    const [selectedCompany, setSelectedCompany] = useState<Company | null>(null);

    useEffect(() => {
        dispatch(fetchCompanies());
    }, [dispatch]);

    useEffect(() => {
        // dispatch(fetchCompanies());
        if (selectedCompany?.id) {
            dispatch(companiesSliceActions.setCompanyId(selectedCompany.id));
        }
    }, [dispatch, selectedCompany]);

    if (error) {
        return (
            <span className="text-destructive">
                Failed to load Companys
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
                    {selectedCompany ? selectedCompany.name : 'Select Company'}
                </Button>
            </PopoverTrigger>

            <PopoverContent className="p-0 w-[280px]" align="start">
                <Command>
                    <CommandInput placeholder="Search companies..." />

                    <CommandList>
                        <CommandEmpty>No results found.</CommandEmpty>

                        <CommandGroup>
                            {companies.map((company) => {
                                const isSelected = selectedCompany?.id === company.id;

                                return (
                                    <CommandItem
                                        key={company.id}
                                        value={company.name}
                                        onSelect={() => {
                                            setSelectedCompany(company);
                                            setOpen(false);
                                        }}
                                        className={cn(
                                            'cursor-pointer',
                                            isSelected && 'bg-primary/10 text-primary font-medium',
                                        )}
                                    >
                                        <span className="flex-1">{company.name}</span>

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
