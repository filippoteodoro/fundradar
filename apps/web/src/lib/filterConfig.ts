import type { FundCategory } from '@fundradar/shared';
import { FUND_CATEGORY_LABELS } from '@fundradar/shared';
import { CATEGORY_COLORS } from './colors';
import { buildAumStops, buildInvestmentStops } from './fundRangeFilters';
import {
  buildFundFilterCatalog,
  buildSectorGroupCounts,
  getSectorGroupOptions,
  deriveFundHqCountry,
  type FilterableFund,
} from './fundFilters';
import { getSectorGroupColor } from './sectorGroups';
import type { DisplaySignalType } from './signalProcessing';

export interface FilterChipOption {
  value: string;
  label: string;
  count: number;
  color?: { bg: string; text: string };
}

export interface FilterSelectOption {
  value: string;
  label: string;
}

export interface DynamicFundFilterSource {
  categories: FundCategory[];
  categoryCounts: Map<FundCategory, number>;
  categoryChipItems: FilterChipOption[];
  categoryDropdownOptions: FilterSelectOption[];
  sectorGroupChipItems: FilterChipOption[];
  sectorGroupDropdownOptions: FilterSelectOption[];
  hqCountryChipItems: FilterChipOption[];
  hqCountryDropdownOptions: FilterSelectOption[];
  aumRangeMax: number;
  invRangeMax: number;
  aumStops: number[];
  invStops: number[];
}

interface RangeFilterable {
  aum_eur?: number | null;
  investment_max_eur?: number | null;
}

/**
 * Single dynamic source for fund-related filters used by Funds, Map, and Signals.
 */
export function buildDynamicFundFilterSource<T extends FilterableFund & RangeFilterable>(funds: T[]): DynamicFundFilterSource {
  const filterCatalog = buildFundFilterCatalog(funds);
  const categories = filterCatalog.categories;
  const categoryCounts = filterCatalog.categoryCounts;

  const categoryChipItems = categories.map((cat) => ({
    value: cat,
    label: FUND_CATEGORY_LABELS[cat],
    count: categoryCounts.get(cat) ?? 0,
    color: CATEGORY_COLORS[cat],
  }));

  const categoryDropdownOptions = categories.map((cat) => ({
    value: cat,
    label: `${FUND_CATEGORY_LABELS[cat]} (${categoryCounts.get(cat) ?? 0})`,
  }));

  const sectorGroupOptions = getSectorGroupOptions(buildSectorGroupCounts(funds));
  const sectorGroupChipItems = sectorGroupOptions.map((group) => ({
    value: group.value,
    label: group.label,
    count: group.count,
    color: getSectorGroupColor(group.value),
  }));
  const sectorGroupDropdownOptions = sectorGroupOptions.map((group) => ({
    value: group.value,
    label: `${group.label} (${group.count})`,
  }));

  const countryCounts = new Map<string, number>();
  for (const fund of funds) {
    const country = deriveFundHqCountry(fund);
    if (!country) continue;
    countryCounts.set(country, (countryCounts.get(country) || 0) + 1);
  }

  const hqCountryChipItems = filterCatalog.hqCountries.map((country) => ({
    value: country,
    label: country,
    count: countryCounts.get(country) ?? 0,
  }));

  const hqCountryDropdownOptions = filterCatalog.hqCountries.map((country) => ({
    value: country,
    label: `${country} (${countryCounts.get(country) ?? 0})`,
  }));

  const aums = funds
    .map((fund) => fund.aum_eur)
    .filter((aum): aum is number => aum != null && aum > 0);
  const aumRangeMax = aums.length > 0 ? Math.max(...aums) : 1000000000;
  const aumStops = buildAumStops(aumRangeMax);

  const investmentMaxes = funds
    .map((fund) => fund.investment_max_eur)
    .filter((inv): inv is number => inv != null && inv > 0);
  const invRangeMax = investmentMaxes.length > 0 ? Math.max(...investmentMaxes) : 0;
  const invStops = buildInvestmentStops(invRangeMax);

  return {
    categories,
    categoryCounts,
    categoryChipItems,
    categoryDropdownOptions,
    sectorGroupChipItems,
    sectorGroupDropdownOptions,
    hqCountryChipItems,
    hqCountryDropdownOptions,
    aumRangeMax,
    invRangeMax,
    aumStops,
    invStops,
  };
}

export const SIGNAL_TYPE_FILTERS: { value: DisplaySignalType | 'all'; label: string }[] = [
  { value: 'all', label: 'All Types' },
  { value: 'investment', label: 'Investments' },
  { value: 'fund', label: 'Funds' },
  { value: 'exit_announced', label: 'Exits' },
  { value: 'debt_financing', label: 'Debt' },
  { value: 'partnership', label: 'Partnerships' },
  { value: 'people', label: 'People' },
  { value: 'portfolio_update', label: 'Portfolio' },
  { value: 'report', label: 'Reports' },
  { value: 'other', label: 'Other' },
];

export function buildSignalTypeChipItems(typeCounts: Map<DisplaySignalType, number>): FilterChipOption[] {
  return SIGNAL_TYPE_FILTERS
    .filter((type): type is { value: DisplaySignalType; label: string } => type.value !== 'all')
    .map((type) => ({
      value: type.value,
      label: type.label,
      count: typeCounts.get(type.value) ?? 0,
    }))
    .filter((item) => item.count > 0);
}
