import { FinalCtaSection } from '@/components/marketing/sections/final-cta';
import { FeaturesSection } from '@/components/marketing/sections/features';
import { HeroSection } from '@/components/marketing/sections/hero';
import { ServicesSection } from '@/components/marketing/sections/services';
import { BlogResourcesSection } from '@/components/marketing/sections/blog-resources';
import { ExpandingPanelSection } from '@/components/marketing/sections/expanding-panel';
import { IndustriesSection } from '@/components/marketing/sections/industries';

export default function MarketingHomePage() {
    return (
        <>
            <HeroSection />
            <ServicesSection />
            <BlogResourcesSection />
            <ExpandingPanelSection />
            <FeaturesSection />
            <IndustriesSection />
            <FinalCtaSection />
        </>
    );
}
