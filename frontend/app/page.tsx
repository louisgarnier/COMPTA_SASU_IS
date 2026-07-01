'use client';

import { useEffect, useState } from 'react';
import { healthAPI } from '@/api/client';

export default function HomePage() {
  const [apiStatus, setApiStatus] = useState<string>('checking...');

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await healthAPI.check();
        setApiStatus(response.status);
      } catch (error) {
        setApiStatus('error');
        console.error('API health check failed:', error);
      }
    };

    checkHealth();
  }, []);

  const backOk = apiStatus === 'healthy';

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50 dark:bg-gray-900">
      <main className="max-w-4xl w-full px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 mb-2">
          LGC
        </h1>
        <p className="text-lg text-gray-600 dark:text-gray-400 mb-8">
          Suivi cashflow SASU — pilotage tréso, forecast &amp; facturation.
        </p>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
          <h2 className="text-xl font-semibold mb-4">État du backend</h2>
          <p className="text-gray-700 dark:text-gray-300 flex items-center gap-2">
            <span
              aria-hidden
              className={`inline-block h-3 w-3 rounded-full ${
                backOk ? 'bg-green-500' : 'bg-red-500'
              }`}
            />
            <span>
              API&nbsp;: <span className="font-mono">{apiStatus}</span>
              {backOk ? ' — back OK' : ''}
            </span>
          </p>
        </div>
      </main>
    </div>
  );
}
