import type { FAQCategory } from '../_data';
import { FAQAccordionItem } from './FAQAccordionItem';

interface Props {
    category: FAQCategory;
}

export function FAQCategorySection({ category }: Props) {
    return (
        <section>
            <h2 className="font-display text-lg font-semibold text-slate-900 sm:text-xl">
                {category.category}
            </h2>
            <div className="mt-3 rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="divide-y divide-slate-200 px-5 sm:px-6">
                    {category.items.map((item) => (
                        <FAQAccordionItem
                            key={item.question}
                            question={item.question}
                            answer={item.answer}
                        />
                    ))}
                </div>
            </div>
        </section>
    );
}
