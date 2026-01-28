import type { ReactNode } from 'react';

type ReportsLayoutProps = {
    children: ReactNode;
};

export default function LegacyRestauranteReportsLayout({ children }: ReportsLayoutProps) {
    return <>{children}</>;
}
