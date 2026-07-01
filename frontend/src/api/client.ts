/**
 * Client API front LGC — communication avec le backend FastAPI local.
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Generic fetch wrapper with error handling
 */
async function fetchAPI<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || `HTTP error! status: ${response.status}`);
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    return await response.json();
  } catch (error) {
    console.error(`API Error (${endpoint}):`, error);
    throw error;
  }
}

/**
 * Health check API
 */
export const healthAPI = {
  check: async (): Promise<{ status: string }> => {
    return fetchAPI<{ status: string }>('/health');
  },
};

// Add more API functions as you develop endpoints
// Example:
// export const exampleAPI = {
//   getAll: async (): Promise<Example[]> => {
//     return fetchAPI<Example[]>('/api/examples');
//   },
// };




