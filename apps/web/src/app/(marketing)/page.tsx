import { FinalCtaSection } from '@/components/marketing/sections/final-cta';
import { HeroSection } from '@/components/marketing/sections/hero';
import { ProductsSection } from '@/components/marketing/sections/products';
import { BlogResourcesSection } from '@/components/marketing/sections/blog-resources';
import { ExpandingPanelSection } from '@/components/marketing/sections/expanding-panel';

export default function MarketingHomePage() {
    return (
        <>
            <HeroSection />
            <BlogResourcesSection />
            <ExpandingPanelSection />
            <ProductsSection />
            <FinalCtaSection />
        </>
    );
}
