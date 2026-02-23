// Shared styles for RIS App - Nubank-inspired Fintech design
import { StyleSheet, Platform } from 'react-native';

// Color palette - keeping original colors with professional fintech touch
export const Colors = {
  primary: '#1e3a5f',      // Dark blue - main brand color
  primaryLight: '#2d5a8a',
  primaryDark: '#0f172a',
  
  accent: '#F5A623',       // Gold/Orange - accent color
  accentLight: '#FFC966',
  accentDark: '#D98C00',
  
  background: '#F8FAFC',   // Light gray background
  surface: '#FFFFFF',      // White cards
  surfaceAlt: '#F1F5F9',   // Subtle gray
  
  text: '#0F172A',         // Primary text
  textSecondary: '#64748B', // Secondary text
  textMuted: '#94A3B8',    // Muted text
  textInverse: '#FFFFFF',  // White text
  
  success: '#10B981',      // Green
  error: '#EF4444',        // Red
  warning: '#F5A623',      // Orange (same as accent)
  info: '#3B82F6',         // Blue
  
  border: '#E2E8F0',
  divider: '#F1F5F9',
};

// Typography - Nubank inspired clean fonts
export const Typography = {
  h1: {
    fontSize: 32,
    fontWeight: '700' as const,
    letterSpacing: -0.5,
    color: Colors.text,
  },
  h2: {
    fontSize: 24,
    fontWeight: '600' as const,
    letterSpacing: -0.3,
    color: Colors.text,
  },
  h3: {
    fontSize: 20,
    fontWeight: '600' as const,
    color: Colors.text,
  },
  subtitle: {
    fontSize: 16,
    fontWeight: '500' as const,
    color: Colors.textSecondary,
  },
  body: {
    fontSize: 16,
    lineHeight: 24,
    color: Colors.text,
  },
  bodySmall: {
    fontSize: 14,
    lineHeight: 20,
    color: Colors.textSecondary,
  },
  caption: {
    fontSize: 12,
    lineHeight: 16,
    color: Colors.textMuted,
  },
  button: {
    fontSize: 16,
    fontWeight: '600' as const,
    letterSpacing: 0.3,
  },
};

// Spacing system
export const Spacing = {
  xs: 4,
  s: 8,
  m: 16,
  l: 24,
  xl: 32,
  xxl: 48,
};

// Border radius
export const BorderRadius = {
  small: 8,
  medium: 12,
  large: 16,
  xl: 20,
  pill: 9999,
};

// Common component styles
export const SharedStyles = StyleSheet.create({
  // Containers
  safeArea: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  scrollContent: {
    flexGrow: 1,
    padding: Spacing.l,
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  
  // Cards
  card: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.large,
    padding: Spacing.l,
    ...Platform.select({
      ios: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.05,
        shadowRadius: 8,
      },
      android: {
        elevation: 2,
      },
      web: {
        boxShadow: '0 2px 8px rgba(0,0,0,0.05)',
      },
    }),
  },
  cardAccent: {
    backgroundColor: Colors.surface,
    borderRadius: BorderRadius.large,
    padding: Spacing.l,
    borderWidth: 2,
    borderColor: Colors.accent,
  },
  
  // Headers
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: Spacing.l,
    paddingVertical: Spacing.m,
    backgroundColor: Colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: Colors.divider,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '600',
    color: Colors.text,
  },
  headerButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: Colors.surfaceAlt,
    justifyContent: 'center',
    alignItems: 'center',
  },
  
  // Inputs
  inputContainer: {
    marginBottom: Spacing.m,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: Colors.textSecondary,
    marginBottom: Spacing.xs,
  },
  input: {
    backgroundColor: Colors.surfaceAlt,
    borderRadius: BorderRadius.medium,
    paddingHorizontal: Spacing.m,
    paddingVertical: Spacing.m,
    fontSize: 16,
    color: Colors.text,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  inputFocused: {
    borderColor: Colors.accent,
    backgroundColor: Colors.surface,
  },
  inputWithIcon: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surfaceAlt,
    borderRadius: BorderRadius.medium,
    paddingHorizontal: Spacing.m,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  inputIcon: {
    marginRight: Spacing.s,
  },
  inputField: {
    flex: 1,
    paddingVertical: Spacing.m,
    fontSize: 16,
    color: Colors.text,
  },
  
  // Buttons
  buttonPrimary: {
    backgroundColor: Colors.primary,
    borderRadius: BorderRadius.pill,
    paddingVertical: Spacing.m,
    paddingHorizontal: Spacing.xl,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonPrimaryText: {
    color: Colors.textInverse,
    fontSize: 16,
    fontWeight: '600',
  },
  buttonAccent: {
    backgroundColor: Colors.accent,
    borderRadius: BorderRadius.pill,
    paddingVertical: Spacing.m,
    paddingHorizontal: Spacing.xl,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonAccentText: {
    color: Colors.textInverse,
    fontSize: 16,
    fontWeight: '600',
  },
  buttonOutline: {
    backgroundColor: 'transparent',
    borderRadius: BorderRadius.pill,
    paddingVertical: Spacing.m,
    paddingHorizontal: Spacing.xl,
    borderWidth: 2,
    borderColor: Colors.primary,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonOutlineText: {
    color: Colors.primary,
    fontSize: 16,
    fontWeight: '600',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  
  // Menu items / List items
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: Colors.surface,
    paddingVertical: Spacing.m,
    paddingHorizontal: Spacing.l,
    borderRadius: BorderRadius.medium,
    marginBottom: Spacing.s,
  },
  menuItemIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: Spacing.m,
  },
  menuItemContent: {
    flex: 1,
  },
  menuItemTitle: {
    fontSize: 16,
    fontWeight: '500',
    color: Colors.text,
  },
  menuItemSubtitle: {
    fontSize: 13,
    color: Colors.textSecondary,
    marginTop: 2,
  },
  
  // Badges
  badge: {
    paddingHorizontal: Spacing.s,
    paddingVertical: 4,
    borderRadius: BorderRadius.small,
  },
  badgeSuccess: {
    backgroundColor: '#D1FAE5',
  },
  badgeSuccessText: {
    color: '#059669',
    fontSize: 12,
    fontWeight: '600',
  },
  badgeWarning: {
    backgroundColor: '#FEF3C7',
  },
  badgeWarningText: {
    color: '#D97706',
    fontSize: 12,
    fontWeight: '600',
  },
  badgeError: {
    backgroundColor: '#FEE2E2',
  },
  badgeErrorText: {
    color: '#DC2626',
    fontSize: 12,
    fontWeight: '600',
  },
  
  // Dividers
  divider: {
    height: 1,
    backgroundColor: Colors.divider,
    marginVertical: Spacing.m,
  },
  
  // Section headers
  sectionHeader: {
    fontSize: 12,
    fontWeight: '700',
    color: Colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: Spacing.m,
    marginTop: Spacing.l,
  },
  
  // Empty states
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: Spacing.xl,
  },
  emptyIcon: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: Colors.surfaceAlt,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: Spacing.l,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: Colors.text,
    textAlign: 'center',
    marginBottom: Spacing.s,
  },
  emptyText: {
    fontSize: 14,
    color: Colors.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
  },
});

export default {
  Colors,
  Typography,
  Spacing,
  BorderRadius,
  SharedStyles,
};
