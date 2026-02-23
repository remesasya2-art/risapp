// Theme constants for RIS App - Nubank-inspired Fintech design
export const colors = {
  primary: {
    main: '#820AD1',
    light: '#A744F2',
    dark: '#5F00A3',
    contrast: '#FFFFFF',
  },
  secondary: {
    main: '#F5A623',
    light: '#FFC966',
    dark: '#D98C00',
    contrast: '#0F172A',
  },
  background: {
    default: '#F8FAFC',
    paper: '#FFFFFF',
    subtle: '#F1F5F9',
  },
  text: {
    primary: '#0F172A',
    secondary: '#64748B',
    disabled: '#94A3B8',
    inverse: '#FFFFFF',
  },
  status: {
    success: '#10B981',
    error: '#EF4444',
    warning: '#F59E0B',
    info: '#3B82F6',
  },
  // Legacy colors for gradual migration
  legacy: {
    darkBlue: '#0f172a',
    gold: '#eab308',
  },
};

export const spacing = {
  xs: 4,
  s: 8,
  m: 16,
  l: 24,
  xl: 32,
  xxl: 48,
};

export const borderRadius = {
  small: 8,
  medium: 12,
  large: 16,
  pill: 9999,
};

export const typography = {
  h1: {
    fontSize: 32,
    fontWeight: '800' as const,
    letterSpacing: -0.5,
  },
  h2: {
    fontSize: 24,
    fontWeight: '700' as const,
    letterSpacing: -0.3,
  },
  h3: {
    fontSize: 20,
    fontWeight: '600' as const,
  },
  body: {
    fontSize: 16,
    lineHeight: 24,
  },
  bodySmall: {
    fontSize: 14,
    lineHeight: 20,
  },
  tiny: {
    fontSize: 12,
    lineHeight: 16,
  },
};

export const shadows = {
  soft: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  medium: {
    shadowColor: '#820AD1',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 12,
    elevation: 5,
  },
};
