import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 8000,
  headers: { Accept: 'application/json' },
})

export async function getApiHealth() {
  const { data } = await apiClient.get('/health')
  return data
}

export default apiClient
