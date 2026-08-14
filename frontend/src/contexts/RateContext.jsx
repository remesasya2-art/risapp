import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../utils/api';

const RateContext = createContext(null);

export function RateProvider({ children }) {
  const [rates, setRates] = useState({
    ris_to_ves: 110,        // Envío: 1 RIS = 110 VES (default)
    ves_to_ris_rate: 140,   // Recarga VES: 140 VES = 1 RIS (default)
    brl_to_ris: 1,          // Recarga PIX: 1 BRL = 1 RIS (default)
  });
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);

  const loadRates = useCallback(async () => {
    try {
      const response = await api.get('/rate');
      const newRates = {
        ris_to_ves: response.data.ris_to_ves || 110,
        ves_to_ris_rate: response.data.ves_to_ris_rate || 140,
        brl_to_ris: response.data.brl_to_ris || 1,
        base_ris_to_ves: response.data.base_ris_to_ves,
        base_ves_to_ris_rate: response.data.base_ves_to_ris_rate,
        auto_rate_enabled: response.data.auto_rate_enabled,
        is_off_hours: response.data.is_off_hours,
        bcv_usd_ves: response.data.bcv_usd_ves,
        bcv_eur_ves: response.data.bcv_eur_ves,
        bcv_value_date: response.data.bcv_value_date,
        updated_at: response.data.updated_at,
        usdtris_to_ves: response.data.usdtris_to_ves,
        usdcris_to_ves: response.data.usdcris_to_ves,
      };
      setRates(newRates);
      setLastUpdated(new Date());
    } catch (error) {
      console.error('Error loading rates:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Load rates immediately on mount
    loadRates();
    
        // Refresh every 5 minutes for more responsive updates
    const interval = setInterval(loadRates, 300000);
    
    return () => clearInterval(interval);
  }, [loadRates]);

  // Force refresh function that can be called from any component
  const refreshRates = useCallback(async () => {
    setLoading(true);
    await loadRates();
  }, [loadRates]);

  return (
    <RateContext.Provider value={{ 
      rates, 
      loading, 
      lastUpdated,
      refreshRates 
    }}>
      {children}
    </RateContext.Provider>
  );
}

export const useRate = () => {
  const context = useContext(RateContext);
  if (!context) {
    throw new Error('useRate must be used within a RateProvider');
  }
  return context;
};
