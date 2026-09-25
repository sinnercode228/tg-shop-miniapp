import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { routes } from './App';
import { useLang } from './i18n';
import { useCart } from './store/cart';

function renderAt(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
}

describe('shop flow (browser fallback, mock API)', () => {
  beforeEach(() => {
    useCart.getState().clear();
    useLang.setState({ lang: 'ru' });
  });

  it('searches the catalog and adds a product to the cart', async () => {
    const user = userEvent.setup();
    renderAt('/');
    const search = await screen.findByPlaceholderText('Поиск по каталогу');
    await user.type(search, 'кения');
    const add = await screen.findByRole('button', { name: /В корзину: Кения/ });
    await user.click(add);
    expect(useCart.getState().lines).toHaveLength(1);
    expect(await screen.findByTestId('main-button')).toHaveTextContent('Корзина · 1');
  });

  it('shows the empty cart state', async () => {
    renderAt('/cart');
    expect(await screen.findByText('Корзина пуста')).toBeInTheDocument();
  });

  it('places a pay-on-receipt pickup order end to end', async () => {
    const user = userEvent.setup();
    useCart.getState().add('gaiwan', 'std', null, 2);
    const router = renderAt('/checkout');

    await user.click(await screen.findByRole('radio', { name: /Самовывоз/ }));
    await user.click(screen.getByRole('button', { name: /При получении/ }));
    await user.type(screen.getByLabelText('Имя'), 'Анна');
    await user.type(screen.getByLabelText('Телефон'), '+7 900 123-45-67');

    const main = await screen.findByTestId('main-button');
    await within(main).findByText(/Заказать/);
    await user.click(main);

    expect(await screen.findByText('Заказ оформлен', {}, { timeout: 3000 })).toBeInTheDocument();
    expect(router.state.location.pathname).toMatch(/^\/orders\/\d+$/);
    expect(useCart.getState().lines).toEqual([]);
  });
});
