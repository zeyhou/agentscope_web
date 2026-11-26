import { Monitor, Moon, Sun } from 'lucide-react';
import { useTheme } from 'next-themes';

import {
	DropdownMenu,
	DropdownMenuContent,
	DropdownMenuLabel,
	DropdownMenuRadioGroup,
	DropdownMenuRadioItem,
	DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { SidebarMenuButton } from '@/components/ui/sidebar';
import { useTranslation } from '@/i18n/useI18n';

const options = [
	{ value: 'light', icon: Sun },
	{ value: 'dark', icon: Moon },
	{ value: 'system', icon: Monitor },
] as const;

export function ThemeSelect() {
	const { theme = 'system', setTheme } = useTheme();
	const { t } = useTranslation();
	const Icon = options.find((option) => option.value === theme)?.icon ?? Monitor;
	const label = t('theme.select', { mode: t(`theme.${theme}`) });

	return (
		<DropdownMenu>
			<DropdownMenuTrigger asChild>
				<SidebarMenuButton
					aria-label={label}
					tooltip={{ children: label, hidden: false }}
					className="justify-center"
				>
					<Icon />
				</SidebarMenuButton>
			</DropdownMenuTrigger>
			<DropdownMenuContent side="right" align="end" sideOffset={8} className="min-w-40">
				<DropdownMenuLabel>{t('theme.label')}</DropdownMenuLabel>
				<DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
					{options.map(({ value, icon: OptionIcon }) => (
						<DropdownMenuRadioItem key={value} value={value}>
							<OptionIcon className="size-4" />
							{t(`theme.${value}`)}
						</DropdownMenuRadioItem>
					))}
				</DropdownMenuRadioGroup>
			</DropdownMenuContent>
		</DropdownMenu>
	);
}
