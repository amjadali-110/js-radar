import axios from 'axios';

// Configure base URL for your backend API
// Use the same hostname the browser is on so the app works when accessed via IP from other devices
const API_BASE_URL = process.env.REACT_APP_API_URL || `http://${window.location.hostname}:3001/api`;

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// API service methods
export const apiService = {
  // Scan management
  createScan: async (scanData, isFormData = false) => {
    const response = await api.post('/scans', scanData, isFormData ? {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    } : undefined);
    return response.data;
  },

  getScans: async () => {
    const response = await api.get('/scans');
    return response.data;
  },

  getScanById: async (scanId) => {
    const response = await api.get(`/scans/${scanId}`);
    return response.data;
  },

  deleteScan: async (scanId) => {
    const response = await api.delete(`/scans/${scanId}`);
    return response.data;
  },

  // Get result counts for a scan (lightweight, no full data)
  getScanCounts: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/counts`);
    return response.data;
  },

  // Scan results
  getScanResults: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/results`);
    return response.data;
  },

  // Secrets
  getSecrets: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/secrets`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '' } });
    return response.data;
  },

  // Endpoints
  getEndpoints: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/endpoints`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '' } });
    return response.data;
  },

  // Parameters
  getParameters: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/parameters`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '' } });
    return response.data;
  },

  // Cloud resources
  getCloudResources: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/cloud-resources`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '', source: filters.source || '' } });
    return response.data;
  },

  getCloudResourceCounts: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/cloud-resources/counts`);
    return response.data;
  },

  // Subdomains
  getSubdomains: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/subdomains`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '', status: filters.status || '' } });
    return response.data;
  },

  getSubdomainCounts: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/subdomains/counts`);
    return response.data;
  },

  // IPs
  getIPs: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/ips`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '' } });
    return response.data;
  },

  // Files
  getFiles: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/files`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '' } });
    return response.data;
  },

  // Emails
  getEmails: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/emails`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '', source: filters.source || '' } });
    return response.data;
  },

  getEmailCounts: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/emails/counts`);
    return response.data;
  },

  // App Links (Play Store, App Store)
  getAppLinks: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/app-links`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '', source: filters.source || '' } });
    return response.data;
  },

  getAppLinkCounts: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/app-links/counts`);
    return response.data;
  },

  // Doc Links (Documentation URLs)
  getDocLinks: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/doc-links`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '', source: filters.source || '' } });
    return response.data;
  },

  getDocLinkCounts: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/doc-links/counts`);
    return response.data;
  },

  // Social Media Links
  getSocialLinks: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/social-links`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '', source: filters.source || '' } });
    return response.data;
  },

  getSocialLinkCounts: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/social-links/counts`);
    return response.data;
  },

  // URLs (all extracted URLs)
  getURLs: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/urls`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '', source: filters.source || '' } });
    return response.data;
  },

  getURLCounts: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/urls/counts`);
    return response.data;
  },

  // Dashboard stats
  getDashboardStats: async () => {
    const response = await api.get('/dashboard/stats');
    return response.data;
  },

  // Start scan
  startScan: async (scanId) => {
    const response = await api.post(`/scans/${scanId}/start`);
    return response.data;
  },

  // Stop scan
  stopScan: async (scanId) => {
    const response = await api.post(`/scans/${scanId}/stop`);
    return response.data;
  },

  // Get input URLs for a scan
  getInputUrls: async (scanId) => {
    const response = await api.get(`/scans/${scanId}/input-urls`);
    return response.data;
  },

  // Get failed JS downloads for a scan
  getFailedDownloads: async (scanId, page = 1, perPage = 50, filters = {}) => {
    const response = await api.get(`/scans/${scanId}/failed-downloads`, { params: { page, per_page: perPage, base_url: filters.baseUrl || '', js_file: filters.jsFile || '' } });
    return response.data;
  },
};

// Request interceptor
api.interceptors.request.use(
  (config) => {
    // Add auth token if available
    const token = localStorage.getItem('authToken');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized access
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
