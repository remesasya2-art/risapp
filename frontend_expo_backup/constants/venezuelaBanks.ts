// Lista de bancos de Venezuela con códigos
export interface BankOption {
  code: string;
  name: string;
  fullName: string;
}

export const VENEZUELA_BANKS: BankOption[] = [
  { code: '0102', name: 'Banco de Venezuela', fullName: 'Banco de Venezuela SAICA' },
  { code: '0104', name: 'Venezolano de Crédito', fullName: 'Banco Venezolano de Crédito SA' },
  { code: '0105', name: 'Mercantil', fullName: 'Banco Mercantil CA' },
  { code: '0108', name: 'Provincial', fullName: 'Banco Provincial, SA' },
  { code: '0114', name: 'Bancaribe', fullName: 'Bancaribe (Banco del Caribe CA)' },
  { code: '0115', name: 'Exterior', fullName: 'Banco Exterior CA' },
  { code: '0128', name: 'Caroní', fullName: 'Banco Caroní CA' },
  { code: '0134', name: 'Banesco', fullName: 'Banesco Banco Universal CA' },
  { code: '0137', name: 'Sofitasa', fullName: 'Banco Sofitasa' },
  { code: '0138', name: 'Plaza', fullName: 'Banco Plaza' },
  { code: '0146', name: 'Bangente', fullName: 'Banco de la Gente Emprendedora (Bangente)' },
  { code: '0151', name: 'Fondo Común', fullName: 'Fondo Común CA' },
  { code: '0156', name: '100% Banco', fullName: '100% Banco, Banco Comercial CA' },
  { code: '0157', name: 'DelSur', fullName: 'DelSur Banco Universal CA' },
  { code: '0163', name: 'Tesoro', fullName: 'Banco del Tesoro CA' },
  { code: '0166', name: 'Agrícola', fullName: 'Banco Agrícola de Venezuela' },
  { code: '0168', name: 'Bancrecer', fullName: 'Bancrecer SA' },
  { code: '0169', name: 'Mi Banco', fullName: 'Mi Banco Banco Microfinanciero CA' },
  { code: '0171', name: 'Activo', fullName: 'Banco Activo CA' },
  { code: '0172', name: 'Bancamiga', fullName: 'Bancamiga Banco Universal CA' },
  { code: '0173', name: 'BID', fullName: 'Banco Internacional de Desarrollo CA' },
  { code: '0174', name: 'Banplus', fullName: 'Banplus Banco Universal CA' },
  { code: '0175', name: 'BDT', fullName: 'Banco Digital de los Trabajadores' },
  { code: '0177', name: 'Banfanb', fullName: 'Banco de la Fuerza Armada Nacional Bolivariana' },
  { code: '0178', name: 'N58', fullName: 'N58 Banco Digital' },
  { code: '0191', name: 'BNC', fullName: 'Banco Nacional de Crédito (BNC)' },
];

export const CEDULA_TYPES = [
  { value: 'V', label: 'V-' },
  { value: 'E', label: 'E-' },
];

export const PHONE_PREFIXES = [
  { value: '0412', label: '0412' },
  { value: '0414', label: '0414' },
  { value: '0416', label: '0416' },
  { value: '0422', label: '0422' },
  { value: '0424', label: '0424' },
  { value: '0426', label: '0426' },
];
