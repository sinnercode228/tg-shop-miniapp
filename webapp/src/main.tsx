import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import './index.css';
import { useLang } from './i18n';
import { initTelegram } from './telegram/sdk';

initTelegram();
document.documentElement.lang = useLang.getState().lang;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
