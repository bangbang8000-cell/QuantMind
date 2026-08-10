import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { isMarketEnabled } from '../../config/marketFlags';

export type AppMarket = 'CN' | 'US' | 'HK' | 'CRYPTO' | 'FUTURES';

export interface UIState {
  theme: 'light' | 'dark';
  sidebarOpen: boolean;
  notifications: any[];
  tradingMode: 'real' | 'simulation';
  currentMarket: AppMarket;
}

const TRADING_MODE_PREF_KEY = 'qm:trading_mode_pref';
const MARKET_PREF_KEY = 'qm:current_market';

const savedMode = localStorage.getItem(TRADING_MODE_PREF_KEY);
const initialTradingMode: 'real' | 'simulation' =
  (savedMode === 'real' || savedMode === 'simulation') ? savedMode : 'simulation';

const savedMarket = localStorage.getItem(MARKET_PREF_KEY);
const validMarkets: AppMarket[] = (['CN', 'US', 'HK', 'CRYPTO', 'FUTURES'] as AppMarket[]).filter((m) => isMarketEnabled(m));
const initialMarket: AppMarket =
  validMarkets.includes(savedMarket as AppMarket) ? (savedMarket as AppMarket) : 'CN';

const initialState: UIState = {
  theme: 'light',
  sidebarOpen: true,
  notifications: [],
  tradingMode: initialTradingMode,
  currentMarket: initialMarket,
};

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    setTheme: (state, action: PayloadAction<'light' | 'dark'>) => {
      state.theme = action.payload;
    },
    toggleSidebar: (state) => {
      state.sidebarOpen = !state.sidebarOpen;
    },
    addNotification: (state, action: PayloadAction<any>) => {
      state.notifications.push(action.payload);
    },
    removeNotification: (state, action: PayloadAction<string>) => {
      state.notifications = state.notifications.filter(n => n.id !== action.payload);
    },
    setTradingMode: (state, action: PayloadAction<'real' | 'simulation'>) => {
      state.tradingMode = action.payload;
    },
    setMarket: (state, action: PayloadAction<AppMarket>) => {
      const market = isMarketEnabled(action.payload) ? action.payload : 'CN';
      state.currentMarket = market;
      localStorage.setItem(MARKET_PREF_KEY, market);
    },
  },
});

export const { setTheme, toggleSidebar, addNotification, removeNotification, setTradingMode, setMarket } = uiSlice.actions;

// Selectors
export const selectCurrentMarket = (state: { ui: UIState }) => state.ui.currentMarket;
export const selectTradingMode = (state: { ui: UIState }) => state.ui.tradingMode;

export default uiSlice.reducer;
