import { FinalCtaSection } from '@/components/marketing/sections/final-cta';
import { FeaturesSection } from '@/components/marketing/sections/features';
import { HeroSection } from '@/components/marketing/sections/hero';
import { HowItWorksSection } from '@/components/marketing/sections/how-it-works';
import { IndustriesSection } from '@/components/marketing/sections/industries';
import { PricingTeaserSection } from '@/components/marketing/sections/pricing-teaser';
import { ProblemSolutionSection } from '@/components/marketing/sections/problem-solution';
import { TrustSection } from '@/components/marketing/sections/trust';

export default function MarketingHomePage() {
    return (
        <>
            <HeroSection />
            <TrustSection />
            <ProblemSolutionSection />
            <FeaturesSection />
            <IndustriesSection />
            <HowItWorksSection />
            <PricingTeaserSection />
            <FinalCtaSection />
        </>
    );
}
