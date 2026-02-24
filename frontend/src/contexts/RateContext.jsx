import { createContext, useContext, useState, useEffect } from 'react';
import api from '../utils/api';

const RateContext = createContext(null);

export function RateProvider({ children }) {
  const [rates, setRates] = useState({
    ris_to_ves: 0,
    ves_to_ris: 0,
    ris_to_brl: 1,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadRates();
    const interval = setInterval(loadRates, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadRates = async () => {
    try {
      const response = await api.get('/rate');
      setRates({
        ris_to_ves: response.data.ris_to_ves || 0,
        ves_to_ris: response.data.ves_to_ris || 0,
        ris_to_brl: response.data.ris_to_brl || 1,
      });
    } catch (error) {
      console.error('Error loading rates:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <RateContext.Provider value={{ rates, loading, refreshRates: loadRates }}>
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
