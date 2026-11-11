import '@fontsource-variable/red-hat-display';
import '@fontsource-variable/red-hat-text';
import '@fontsource-variable/red-hat-mono';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';
createRoot(document.getElementById('root')!).render(<StrictMode>
    <App />
  </StrictMode>);
