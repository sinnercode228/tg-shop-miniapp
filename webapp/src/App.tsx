import { AnimatePresence, motion } from 'motion/react';
import { useEffect } from 'react';
import {
  createHashRouter,
  Outlet,
  RouterProvider,
  ScrollRestoration,
  useLocation,
} from 'react-router';
import { DemoInvoiceSheet, FallbackMainButton, Footer, Header } from './components/Chrome';
import { Button, EmptyState } from './components/ui';
import { useT } from './i18n';
import { CartPage } from './pages/CartPage';
import { CatalogPage } from './pages/CatalogPage';
import { CheckoutPage } from './pages/CheckoutPage';
import { OrderPage } from './pages/OrderPage';
import { OrdersPage } from './pages/OrdersPage';
import { ProductPage } from './pages/ProductPage';
import { useCatalog } from './store/catalog';

function Layout() {
  const location = useLocation();
  const { t } = useT();
  const { error, load } = useCatalog();
  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="flex min-h-dvh flex-col">
      <Header />
      <main className="mx-auto w-full max-w-xl flex-1 px-4 pt-4 pb-28">
        {error ? (
          <EmptyState
            icon="⚠️"
            title={t('error')}
            hint={error}
            action={<Button onClick={() => void load()}>{t('retry')}</Button>}
          />
        ) : (
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.16, ease: 'easeOut' }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        )}
        <Footer />
      </main>
      <FallbackMainButton />
      <DemoInvoiceSheet />
      <ScrollRestoration />
    </div>
  );
}

export const routes = [
  {
    element: <Layout />,
    children: [
      { path: '/', element: <CatalogPage /> },
      { path: '/product/:id', element: <ProductPage /> },
      { path: '/cart', element: <CartPage /> },
      { path: '/checkout', element: <CheckoutPage /> },
      { path: '/orders', element: <OrdersPage /> },
      { path: '/orders/:id', element: <OrderPage /> },
      { path: '*', element: <CatalogPage /> },
    ],
  },
];

// Hash routing keeps deep links working on GitHub Pages and inside Telegram's WebView.
const router = createHashRouter(routes);

export function App() {
  return <RouterProvider router={router} />;
}
