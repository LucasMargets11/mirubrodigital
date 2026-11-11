import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ContactForm } from '../_components/ContactForm';
import { ContactTopics } from '../_components/ContactTopics';
import { CONTACT_TOPICS, INQUIRY_OPTIONS } from '../_constants';
import { SupportForm } from '../../soporte/_components/SupportForm';
import { SupportTopics } from '../../soporte/_components/SupportTopics';
import { PRODUCT_OPTIONS, SUPPORT_TOPICS } from '../../soporte/_constants';
import { buildContactWhatsAppMessage } from '../_utils';
import { buildSupportMessage } from '../../soporte/_utils';

afterEach(cleanup);

describe('Turnos contact and support options', () => {
  it('selects Turnos in the existing contact form and preserves message generation', () => {
    render(
      <>
        <ContactTopics />
        <ContactForm />
      </>,
    );
    const option = screen.getByRole('option', { name: 'Quiero más información sobre Turnos' });
    const select = option.closest('select')!;
    fireEvent.change(select, { target: { value: 'Quiero más información sobre Turnos' } });
    expect(select).toHaveValue('Quiero más información sobre Turnos');
    expect(INQUIRY_OPTIONS.filter((entry) => entry.label.includes('Turnos'))).toHaveLength(1);
    expect(CONTACT_TOPICS).toContain('Obtener más información sobre Turnos');
    expect(screen.getAllByRole('listitem')).toHaveLength(CONTACT_TOPICS.length);
    expect(
      buildContactWhatsAppMessage({
        fullName: 'Prueba',
        businessName: 'Local',
        email: 'test@example.com',
        inquiryType: select.value,
        message: 'Consulta sobre la agenda',
        preferredChannel: 'Email',
        phone: '',
      }),
    ).toContain('Quiero más información sobre Turnos');
  });

  it('selects Turnos in the existing support form and preserves message generation', () => {
    render(
      <>
        <SupportTopics />
        <SupportForm />
      </>,
    );
    const option = screen.getByRole('option', { name: 'Turnos' });
    const select = option.closest('select')!;
    fireEvent.change(select, { target: { value: 'Turnos' } });
    expect(select).toHaveValue('Turnos');
    expect(PRODUCT_OPTIONS.filter((entry) => entry.value === 'Turnos')).toHaveLength(1);
    expect(SUPPORT_TOPICS).toContain('Turnos');
    expect(screen.getAllByRole('listitem')).toHaveLength(SUPPORT_TOPICS.length);
    expect(
      buildSupportMessage({
        businessName: 'Local',
        email: 'test@example.com',
        product: select.value,
        description: 'Consulta sobre la agenda',
        extra: '',
      }),
    ).toContain('Turnos');
  });
});
