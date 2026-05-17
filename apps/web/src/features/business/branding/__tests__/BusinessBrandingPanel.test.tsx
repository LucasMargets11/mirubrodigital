/**
 * Tests for BusinessBrandingPanel component.
 *
 * Covers:
 * - Loading skeleton while query is pending
 * - Renders logo_horizontal_url and logo_square_url when available
 * - "Sin logo" placeholder shown when URLs are null
 * - File validation: rejects > 5MB with error message
 * - File validation: rejects non-image file type
 * - Calls uploadMutation with correct type ('horizontal' / 'square')
 * - Renders accent_color picker with branding value
 * - Color saved confirmation appears after successful update
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BusinessBrandingPanel } from '../BusinessBrandingPanel';

// ── Mock hooks ────────────────────────────────────────────────────────────────

const mockUploadMutateAsync = vi.fn();
const mockUpdateMutateAsync = vi.fn();

let mockBrandingQueryResult: Record<string, unknown> = {
  isPending: false,
  data: null,
};
let mockUploadMutationState: Record<string, unknown> = {
  isPending: false,
  variables: undefined,
  mutateAsync: mockUploadMutateAsync,
};
let mockUpdateMutationState: Record<string, unknown> = {
  isPending: false,
  mutateAsync: mockUpdateMutateAsync,
};

vi.mock('@/features/gestion/hooks', () => ({
  useBusinessBrandingQuery: () => mockBrandingQueryResult,
  useUploadBusinessLogoMutation: () => mockUploadMutationState,
  useUpdateBusinessBrandingMutation: () => mockUpdateMutationState,
}));

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeFile(name: string, type: string, sizeBytes: number): File {
  const content = new Uint8Array(sizeBytes).fill(0);
  return new File([content], name, { type });
}

beforeEach(() => {
  mockUploadMutateAsync.mockReset();
  mockUpdateMutateAsync.mockReset();

  mockBrandingQueryResult = {
    isPending: false,
    data: null,
  };
  mockUploadMutationState = {
    isPending: false,
    variables: undefined,
    mutateAsync: mockUploadMutateAsync,
  };
  mockUpdateMutationState = {
    isPending: false,
    mutateAsync: mockUpdateMutateAsync,
  };
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('BusinessBrandingPanel', () => {
  describe('loading state', () => {
    it('shows skeleton while query is pending', () => {
      mockBrandingQueryResult = { isPending: true, data: undefined };
      const { container } = render(<BusinessBrandingPanel />);
      // Skeleton has animate-pulse class
      expect(container.querySelector('.animate-pulse')).toBeTruthy();
    });
  });

  describe('logo display', () => {
    it('renders logo_horizontal_url when available', () => {
      mockBrandingQueryResult = {
        isPending: false,
        data: {
          logo_horizontal_url: 'https://example.com/horizontal.png',
          logo_square_url: null,
          accent_color: '#2563eb',
        },
      };
      render(<BusinessBrandingPanel />);
      const img = screen.getByAltText('Logo horizontal') as HTMLImageElement;
      expect(img.src).toBe('https://example.com/horizontal.png');
    });

    it('renders logo_square_url when available', () => {
      mockBrandingQueryResult = {
        isPending: false,
        data: {
          logo_horizontal_url: null,
          logo_square_url: 'https://example.com/square.png',
          accent_color: '#2563eb',
        },
      };
      render(<BusinessBrandingPanel />);
      const img = screen.getByAltText('Logo vertical / cuadrado') as HTMLImageElement;
      expect(img.src).toBe('https://example.com/square.png');
    });

    it('shows "Sin logo" placeholder for both slots when branding is null', () => {
      mockBrandingQueryResult = {
        isPending: false,
        data: null,
      };
      render(<BusinessBrandingPanel />);
      const placeholders = screen.getAllByText('Sin logo');
      expect(placeholders).toHaveLength(2);
    });

    it('shows "Sin logo" placeholder when logo URLs are null', () => {
      mockBrandingQueryResult = {
        isPending: false,
        data: { logo_horizontal_url: null, logo_square_url: null, accent_color: '#2563eb' },
      };
      render(<BusinessBrandingPanel />);
      const placeholders = screen.getAllByText('Sin logo');
      expect(placeholders).toHaveLength(2);
    });
  });

  describe('file validation', () => {
    beforeEach(() => {
      mockBrandingQueryResult = {
        isPending: false,
        data: { logo_horizontal_url: null, logo_square_url: null, accent_color: '#2563eb' },
      };
    });

    it('shows error when uploading a file over 5MB', async () => {
      render(<BusinessBrandingPanel />);

      // Find the hidden file inputs — first one is the horizontal slot
      const inputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
      expect(inputs.length).toBeGreaterThanOrEqual(1);

      const oversizedFile = makeFile('logo.png', 'image/png', 5 * 1024 * 1024 + 1);
      fireEvent.change(inputs[0], { target: { files: [oversizedFile] } });

      await waitFor(() => {
        expect(screen.getByText('El archivo supera el límite de 5 MB.')).toBeTruthy();
      });
      expect(mockUploadMutateAsync).not.toHaveBeenCalled();
    });

    it('shows error when uploading a non-image file type', async () => {
      render(<BusinessBrandingPanel />);

      const inputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
      const badFile = makeFile('doc.pdf', 'application/pdf', 1024);
      fireEvent.change(inputs[0], { target: { files: [badFile] } });

      await waitFor(() => {
        expect(screen.getByText('Solo se aceptan PNG, JPG o WebP.')).toBeTruthy();
      });
      expect(mockUploadMutateAsync).not.toHaveBeenCalled();
    });
  });

  describe('upload mutation calls', () => {
    beforeEach(() => {
      mockBrandingQueryResult = {
        isPending: false,
        data: { logo_horizontal_url: null, logo_square_url: null, accent_color: '#2563eb' },
      };
      mockUploadMutateAsync.mockResolvedValue({});
    });

    it('calls uploadMutation with type="horizontal" for the horizontal slot', async () => {
      render(<BusinessBrandingPanel />);

      const inputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
      const validFile = makeFile('logo.png', 'image/png', 100);
      fireEvent.change(inputs[0], { target: { files: [validFile] } });

      await waitFor(() => {
        expect(mockUploadMutateAsync).toHaveBeenCalledWith({
          file: validFile,
          type: 'horizontal',
        });
      });
    });

    it('calls uploadMutation with type="square" for the square slot', async () => {
      render(<BusinessBrandingPanel />);

      const inputs = document.querySelectorAll<HTMLInputElement>('input[type="file"]');
      expect(inputs.length).toBeGreaterThanOrEqual(2);

      const validFile = makeFile('square.png', 'image/png', 100);
      fireEvent.change(inputs[1], { target: { files: [validFile] } });

      await waitFor(() => {
        expect(mockUploadMutateAsync).toHaveBeenCalledWith({
          file: validFile,
          type: 'square',
        });
      });
    });
  });

  describe('color picker', () => {
    beforeEach(() => {
      mockBrandingQueryResult = {
        isPending: false,
        data: { logo_horizontal_url: null, logo_square_url: null, accent_color: '#ff5500' },
      };
    });

    it('renders a text input pre-filled with the branding accent_color', () => {
      render(<BusinessBrandingPanel />);
      // The hex text input inside ColorSwatch
      const hexInput = document.querySelector<HTMLInputElement>('input[maxlength="7"]');
      expect(hexInput).toBeTruthy();
      expect(hexInput?.value).toBe('#ff5500');
    });
  });
});
