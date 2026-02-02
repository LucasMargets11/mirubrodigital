import { menuFontsVariablesClassName } from '@/lib/fonts';

export default function PublicMenuLayoutWrapper({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={menuFontsVariablesClassName}>
      {children}
    </div>
  );
}
