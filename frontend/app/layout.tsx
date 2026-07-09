import type { Metadata } from 'next';
import './globals.css';
import { Nav } from '@/components/Nav';

export const metadata: Metadata = {
  title: 'LGC — Compta SASU',
  description: 'Suivi cashflow SASU : tréso, forecast & facturation.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr">
      <body>
        <div className="flex min-h-screen">
          <Nav />
          {/* pt-20 mobile : dégage la barre supérieure fixe (hamburger). */}
          <main className="min-w-0 flex-1 px-4 pb-6 pt-20 lg:px-10 lg:py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
