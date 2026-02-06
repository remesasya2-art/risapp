import { Dimensions, Platform, StyleSheet } from 'react-native';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

// Breakpoints
export const BREAKPOINTS = {
  mobile: 480,
  tablet: 768,
  desktop: 1024,
  wide: 1200,
};

// Check device type
export const isWeb = Platform.OS === 'web';
export const isMobile = SCREEN_WIDTH < BREAKPOINTS.tablet;
export const isTablet = SCREEN_WIDTH >= BREAKPOINTS.tablet && SCREEN_WIDTH < BREAKPOINTS.desktop;
export const isDesktop = SCREEN_WIDTH >= BREAKPOINTS.desktop;

// Get container width based on screen size
export const getContainerWidth = () => {
  if (SCREEN_WIDTH >= BREAKPOINTS.wide) return 480; // Max width on very large screens
  if (SCREEN_WIDTH >= BREAKPOINTS.desktop) return 440;
  if (SCREEN_WIDTH >= BREAKPOINTS.tablet) return 400;
  return SCREEN_WIDTH; // Full width on mobile
};

// Get responsive padding
export const getResponsivePadding = () => {
  if (isDesktop) return 40;
  if (isTablet) return 32;
  return 20;
};

// Responsive styles for web
export const webStyles = StyleSheet.create({
  // Container that centers content on large screens
  centeredContainer: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: '#f5f7fa',
  },
  
  // Inner container with max-width
  innerContainer: {
    width: '100%',
    maxWidth: getContainerWidth(),
    flex: 1,
    backgroundColor: '#f8fafc',
    ...(isWeb && isDesktop ? {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.1,
      shadowRadius: 20,
      borderLeftWidth: 1,
      borderRightWidth: 1,
      borderColor: '#e2e8f0',
    } : {}),
  },
  
  // Desktop sidebar placeholder
  desktopHeader: {
    backgroundColor: '#1e40af',
    paddingVertical: 20,
    paddingHorizontal: 24,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  
  desktopHeaderTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#fff',
  },
  
  desktopHeaderSubtitle: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.8)',
  },
});

// Helper function to get responsive value
export const responsive = (mobile: number, tablet: number, desktop: number) => {
  if (isDesktop) return desktop;
  if (isTablet) return tablet;
  return mobile;
};

// Helper for responsive font sizes
export const responsiveFontSize = (baseSize: number) => {
  if (isDesktop) return baseSize * 1.1;
  if (isTablet) return baseSize * 1.05;
  return baseSize;
};

export default {
  BREAKPOINTS,
  isWeb,
  isMobile,
  isTablet,
  isDesktop,
  getContainerWidth,
  getResponsivePadding,
  webStyles,
  responsive,
  responsiveFontSize,
};
