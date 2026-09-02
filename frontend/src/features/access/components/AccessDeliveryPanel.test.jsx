import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AccessDeliveryPanel from './AccessDeliveryPanel.jsx'

describe('AccessDeliveryPanel', () => {
  it('muestra el fallo persistido y permite reintentar', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    render(
      <AccessDeliveryPanel
        access={{
          estado: 'fallido',
          intentos: 1,
          primer_ingreso: true,
          ultimo_error: 'El servicio de correo no está configurado.',
        }}
        onRetry={onRetry}
      />,
    )

    expect(screen.getByText('Envío fallido')).toBeInTheDocument()
    expect(
      screen.getByText('El servicio de correo no está configurado.'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reintentar envío' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('no ofrece la contraseña temporal después de activar la cuenta', () => {
    render(
      <AccessDeliveryPanel
        access={{
          estado: 'enviado',
          intentos: 1,
          primer_ingreso: false,
        }}
      />,
    )

    expect(screen.getByText('Cuenta activa')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('permite reenviar credenciales mientras la cuenta no fue activada', async () => {
    const onRetry = vi.fn()
    const user = userEvent.setup()
    render(
      <AccessDeliveryPanel
        access={{
          estado: 'enviado',
          intentos: 1,
          primer_ingreso: true,
        }}
        onRetry={onRetry}
      />,
    )

    expect(screen.getByText('Credenciales enviadas')).toBeInTheDocument()
    await user.click(
      screen.getByRole('button', { name: 'Reenviar credenciales' }),
    )
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
