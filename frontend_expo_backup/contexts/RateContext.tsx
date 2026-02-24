import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface RateData {
  ris_to_ves: number;
  ves_to_ris: number;
  ris_to_brl: number;
  updated_at: string;
  updated_by: string;
}

interface RateContextType {
  rates: RateData;
  loading: boolean;
  error: string | null;
  refreshRate: () => Promise<void>;
  lastUpdate: Date | null;
}

const defaultRates: RateData = {
  ris_to_ves: 100,
  ves_to_ris: 120,
  ris_to_brl: 1,
  updated_at: '',
  updated_by: '',
};

const RateContext = createContext<RateContextType>({
  rates: defaultRates,
  loading: true,
  error: null,
  refreshRate: async () => {},
  lastUpdate: null,
});

export const useRate = () => useContext(RateContext);

interface RateProviderProps {
  children: ReactNode;
}

export const RateProvider: React.FC<RateProviderProps> = ({ children }) => {
  const [rates, setRates] = useState<RateData>(defaultRates);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  const fetchRate = useCallback(async () => {
    try {
      console.log('[RateContext] Fetching rate from:', `${BACKEND_URL}/api/rate`);
      const response = await axios.get(`${BACKEND_URL}/api/rate`);
      
      const newRates: RateData = {
        ris_to_ves: response.data.ris_to_ves || 100,
        ves_to_ris: response.data.ves_to_ris || 120,
        ris_to_brl: response.data.ris_to_brl || 1,
        updated_at: response.data.updated_at || '',
        updated_by: response.data.updated_by || '',
      };
      
      console.log('[RateContext] Rate updated:', newRates);
      setRates(newRates);
      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      console.error('[RateContext] Error fetching rate:', err);
      setError('Error al cargar la tasa');
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchRate();
  }, [fetchRate]);

  // Auto-refresh every 10 seconds for real-time updates
  useEffect(() => {
    const interval = setInterval(() => {
      fetchRate();
    }, 10000); // 10 seconds for near real-time

    return () => clearInterval(interval);
  }, [fetchRate]);

  const refreshRate = useCallback(async () => {
    setLoading(true);
    await fetchRate();
  }, [fetchRate]);

  return (
    <RateContext.Provider value={{ rates, loading, error, refreshRate, lastUpdate }}>
      {children}
    </RateContext.Provider>
  );
};

export default RateContext;
