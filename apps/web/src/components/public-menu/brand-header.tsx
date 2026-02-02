
import { LayoutTheme } from "@/features/menu/types";
import { cn } from "@/lib/utils";

interface MenuBrandHeaderProps {
  brandDetails: {
    name: string;
    description?: string;
  };
  theme: LayoutTheme;
}

export function MenuBrandHeader({ brandDetails, theme }: MenuBrandHeaderProps) {
  const logoUrl = theme.menuLogoUrl;
  const position = theme.menuLogoPosition || 'top_center';
  const size = theme.menuLogoSize || 'md';

  const imgSizeClass = {
      sm: 'h-8 lg:h-10',
      md: 'h-10 lg:h-16', 
      lg: 'h-16 lg:h-[88px]'
  }[size];

  // Common title/desc rendering to avoid duplication
  const TitleAndDesc = () => (
    <>
      <h1 className="font-semibold tracking-tight font-[family-name:var(--menu-font-heading)]"
          style={{ fontSize: `calc(var(--menu-size-heading) * 2)`, lineHeight: 1.1 }}
      >
          {brandDetails.name}
      </h1>
      {brandDetails.description && (
            <p className="mx-auto mt-4 max-w-2xl text-[var(--menu-muted)]"
              style={{ fontSize: `calc(var(--menu-size-body) * 1.1)` }}
            >
              {brandDetails.description}
          </p>
      )}
    </>
  );

  if (!logoUrl || position === 'watermark') {
    return (
       <div className="mb-12 text-center lg:mb-16">
          <TitleAndDesc />
      </div>
    );
  }

  return (
    <div className="mb-12 lg:mb-16 w-full">
        {position === 'top_center' && (
             <div className="flex flex-col items-center text-center">
                 <img src={logoUrl} alt={`Logo de ${brandDetails.name}`} className={cn("mb-6 object-contain", imgSizeClass)} />
                 <TitleAndDesc />
             </div>
        )}

        {position === 'title_left' && (
             <div className="flex flex-col items-center gap-6">
                <div className="flex items-center gap-4 lg:gap-6 justify-center flex-wrap">
                    <img src={logoUrl} alt={`Logo de ${brandDetails.name}`} className={cn("object-contain", imgSizeClass)} />
                    <h1 className="font-semibold tracking-tight font-[family-name:var(--menu-font-heading)]"
                        style={{ fontSize: `calc(var(--menu-size-heading) * 2)`, lineHeight: 1.1 }}
                    >
                        {brandDetails.name}
                    </h1>
                </div>
                 {brandDetails.description && (
                   <p className="mx-auto max-w-2xl text-center text-[var(--menu-muted)]"
                       style={{ fontSize: `calc(var(--menu-size-body) * 1.1)` }}
                   >
                      {brandDetails.description}
                  </p>
                )}
             </div>
        )}

        {position === 'top_right_small' && (
            <div className="relative pt-2">
                 <div className="absolute -top-2 right-0 lg:top-0">
                    <img src={logoUrl} alt={`Logo de ${brandDetails.name}`} className={cn("object-contain", imgSizeClass)} />
                 </div>
                 <div className="text-center px-10 lg:px-0">
                    <TitleAndDesc />
                 </div>
            </div>
        )}
    </div>
  );
}
