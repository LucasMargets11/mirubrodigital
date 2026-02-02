import { cn } from '@/lib/utils';

interface MarketingContainerProps {
    children: React.ReactNode;
    className?: string;
}

export function MarketingContainer({ children, className }: MarketingContainerProps) {
    return (
        <div className={cn("mx-auto w-full max-w-[1400px] px-6 md:px-10 lg:px-16", className)}>
            {children}
        </div>
    );
}
