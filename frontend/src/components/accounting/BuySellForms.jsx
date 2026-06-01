import { fmt } from './constants';

export const BuySellForms = ({
  activeRoute, buyForm, setBuyForm, sellForm, setSellForm,
  banks, recentOps, submitting, registerBuy, registerSell
}) => (
  <div style={{ backgroundColor: '#fffbeb', border: '1px solid #fbbf24', borderRadius: '14px', padding: '20px', marginBottom: '16px' }}>
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
      {/* BUY */}
      <div style={{ backgroundColor: '#fff', borderRadius: '12px', padding: '16px', border: '1px solid #e5e7eb' }}>
        <h5 style={{ fontSize: '14px', fontWeight: '700', color: '#1e3a5f', margin: '0 0 12px 0' }}>REGISTRAR COMPRA USDT</h5>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
          <div>
            <label style={{ fontSize: '11px', color: '#6b7280', display: 'block', marginBottom: '2px' }}>
              {activeRoute === 'brl_ves' ? 'BRL Pagados *' : 'VES Pagados *'}
            </label>
            <input type="number" step="0.01" value={buyForm.amount_fiat} onChange={e => setBuyForm(f => ({ ...f, amount_fiat: e.target.value }))}
              placeholder="0.00" style={{ padding: '12px', borderRadius: '8px', border: '1px solid #d1d5db', width: '100%', boxSizing: 'border-box', fontSize: '16px' }}
              data-testid="buy-amount-fiat"
            />
          </div>
          <div>
            <label style={{ fontSize: '11px', color: '#6b7280', display: 'block', marginBottom: '2px' }}>Tasa de Compra *</label>
            <input type="number" step="0.0001" value={buyForm.rate || ''} onChange={e => setBuyForm(f => ({ ...f, rate: e.target.value }))}
              placeholder="Ej: 5.17" style={{ padding: '12px', borderRadius: '8px', border: '1px solid #d1d5db', width: '100%', boxSizing: 'border-box', fontSize: '16px' }}
              data-testid="buy-rate-input"
            />
          </div>
        </div>
        {buyForm.amount_fiat && buyForm.rate && parseFloat(buyForm.rate) > 0 && (
          <div style={{ padding: '10px', backgroundColor: '#dbeafe', borderRadius: '8px', marginBottom: '8px', textAlign: 'center' }}>
            <p style={{ fontSize: '12px', color: '#2563eb', margin: '0 0 2px 0' }}>USDT Recibidos</p>
            <p style={{ fontSize: '22px', fontWeight: '700', color: '#1e3a5f', margin: 0 }}>
              {fmt(parseFloat(buyForm.amount_fiat) / parseFloat(buyForm.rate))} USDT
            </p>
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '10px' }}>
          <div>
            <label style={{ fontSize: '11px', color: '#6b7280', display: 'block', marginBottom: '2px' }}>Banco Origen *</label>
            <select value={buyForm.bank_id} onChange={e => setBuyForm(f => ({ ...f, bank_id: e.target.value }))}
              style={{ padding: '12px', borderRadius: '8px', border: '1px solid #d1d5db', width: '100%', boxSizing: 'border-box', fontSize: '14px' }}
              data-testid="buy-bank-select"
            >
              <option value="">-- Seleccionar --</option>
              {banks.map(b => <option key={b.bank_id} value={b.bank_id}>{b.name} ({fmt(b.balance)} {b.currency})</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '11px', color: '#6b7280', display: 'block', marginBottom: '2px' }}>Proveedor</label>
            <input type="text" value={buyForm.provider} onChange={e => setBuyForm(f => ({ ...f, provider: e.target.value }))}
              placeholder="Nombre" style={{ padding: '12px', borderRadius: '8px', border: '1px solid #d1d5db', width: '100%', boxSizing: 'border-box', fontSize: '14px' }}
            />
          </div>
        </div>
        <button onClick={registerBuy} disabled={submitting}
          style={{ width: '100%', padding: '14px', borderRadius: '10px', border: 'none', backgroundColor: '#1e3a5f', color: '#fff', fontSize: '15px', fontWeight: '700', cursor: 'pointer', opacity: submitting ? 0.6 : 1 }}
          data-testid="register-buy-btn"
        >Registrar Compra</button>
      </div>

      {/* SELL */}
      <div style={{ backgroundColor: '#fff', borderRadius: '12px', padding: '16px', border: '1px solid #e5e7eb' }}>
        <h5 style={{ fontSize: '14px', fontWeight: '700', color: '#166534', margin: '0 0 12px 0' }}>REGISTRAR VENTA USDT</h5>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '8px' }}>
          <div>
            <label style={{ fontSize: '11px', color: '#6b7280', display: 'block', marginBottom: '2px' }}>
              {activeRoute === 'brl_ves' ? 'VES Recibidos *' : 'BRL Recibidos *'}
            </label>
            <input type="number" step="0.01" value={sellForm.amount_fiat || ''} onChange={e => setSellForm(f => ({ ...f, amount_fiat: e.target.value }))}
              placeholder="0.00" style={{ padding: '12px', borderRadius: '8px', border: '1px solid #d1d5db', width: '100%', boxSizing: 'border-box', fontSize: '16px' }}
              data-testid="sell-amount-fiat"
            />
          </div>
          <div>
            <label style={{ fontSize: '11px', color: '#6b7280', display: 'block', marginBottom: '2px' }}>Tasa de Venta *</label>
            <input type="number" step="0.0001" value={sellForm.rate || ''} onChange={e => setSellForm(f => ({ ...f, rate: e.target.value }))}
              placeholder="Ej: 657.15" style={{ padding: '12px', borderRadius: '8px', border: '1px solid #d1d5db', width: '100%', boxSizing: 'border-box', fontSize: '16px' }}
              data-testid="sell-rate-input"
            />
          </div>
        </div>
        {sellForm.amount_fiat && sellForm.rate && parseFloat(sellForm.rate) > 0 && (
          <div style={{ padding: '10px', backgroundColor: '#dcfce7', borderRadius: '8px', marginBottom: '8px', textAlign: 'center' }}>
            <p style={{ fontSize: '12px', color: '#16a34a', margin: '0 0 2px 0' }}>USDT Vendidos</p>
            <p style={{ fontSize: '22px', fontWeight: '700', color: '#166534', margin: 0 }}>
              {fmt(parseFloat(sellForm.amount_fiat) / parseFloat(sellForm.rate))} USDT
            </p>
          </div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '10px' }}>
          <div>
            <label style={{ fontSize: '11px', color: '#6b7280', display: 'block', marginBottom: '2px' }}>Banco Receptor *</label>
            <select value={sellForm.bank_id} onChange={e => setSellForm(f => ({ ...f, bank_id: e.target.value }))}
              style={{ padding: '12px', borderRadius: '8px', border: '1px solid #d1d5db', width: '100%', boxSizing: 'border-box', fontSize: '14px' }}
              data-testid="sell-bank-select"
            >
              <option value="">-- Seleccionar --</option>
              {banks.map(b => <option key={b.bank_id} value={b.bank_id}>{b.name} ({fmt(b.balance)} {b.currency})</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: '11px', color: '#6b7280', display: 'block', marginBottom: '2px' }}>Proveedor</label>
            <input type="text" value={sellForm.provider} onChange={e => setSellForm(f => ({ ...f, provider: e.target.value }))}
              placeholder="Nombre" style={{ padding: '12px', borderRadius: '8px', border: '1px solid #d1d5db', width: '100%', boxSizing: 'border-box', fontSize: '14px' }}
            />
          </div>
        </div>
        <button onClick={registerSell} disabled={submitting}
          style={{ width: '100%', padding: '14px', borderRadius: '10px', border: 'none', backgroundColor: '#166534', color: '#fff', fontSize: '15px', fontWeight: '700', cursor: 'pointer', opacity: submitting ? 0.6 : 1 }}
          data-testid="register-sell-btn"
        >Registrar Venta</button>
      </div>
    </div>

    {recentOps.length > 0 && (
      <div style={{ marginTop: '16px' }}>
        <h5 style={{ fontSize: '13px', fontWeight: '600', color: '#78716c', margin: '0 0 8px 0' }}>Ultimas operaciones</h5>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          {recentOps.slice(0, 5).map(op => (
            <div key={op.operation_id} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 10px', backgroundColor: '#fff', borderRadius: '8px', fontSize: '12px' }}>
              <span style={{ fontWeight: '600', color: op.operation_type === 'buy' ? '#2563eb' : '#16a34a', minWidth: '60px' }}>
                {op.operation_type === 'buy' ? 'COMPRA' : 'VENTA'}
              </span>
              <span>{op.amount_usdt} USDT</span>
              <span style={{ color: '#6b7280' }}>@ {fmt(op.rate, 4)}</span>
              <span style={{ color: '#6b7280' }}>= {fmt(op.total_fiat)}</span>
              <span style={{ color: '#9ca3af' }}>{op.bank_name}</span>
              <span style={{ color: '#9ca3af', marginLeft: 'auto' }}>{op.date}</span>
            </div>
          ))}
        </div>
      </div>
    )}
  </div>
);
