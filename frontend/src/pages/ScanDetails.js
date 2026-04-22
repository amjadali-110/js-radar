import React, { useState, useEffect, useCallback, useRef, memo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Shield,
  Key,
  Globe,
  FileText,
  Cloud,
  Server,
  Code,
  Download,
  Copy,
  ExternalLink,
  Link2,
  Share2,
  AlertTriangle,
  CheckCircle,
  Clock,
  Play,
  Pause,
  RefreshCw,
  Eye,
  EyeOff,
  Mail,
  Smartphone,
  BookOpen,
  Filter,
  X,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  HardDrive,
  Cpu,
  XCircle,
  HelpCircle
} from 'lucide-react';
import { apiService } from '../services/api';

const ITEMS_PER_PAGE = 50;
const SCAN_TYPE_LABELS = {
  full: 'Full Scan',
  js_urls: 'JS URLs Scan',
  file: 'File Scan',
};

// API fetcher map - maps tab id to api method name
const TAB_API_MAP = {
  secrets: 'getSecrets',
  endpoints: 'getEndpoints',
  cloud: 'getCloudResources',
  subdomains: 'getSubdomains',
  ips: 'getIPs',
  files: 'getFiles',
  emails: 'getEmails',
  applinks: 'getAppLinks',
  doclinks: 'getDocLinks',
  sociallinks: 'getSocialLinks',
  urls: 'getURLs'
};

// FilterBar with local state to keep cursor stable during parent re-renders
const FilterBar = memo(({ section, onFilterChange, onClearFilters, filters, hideBaseUrl }) => {
  const [localBaseUrl, setLocalBaseUrl] = useState(filters.baseUrl);
  const [localJsFile, setLocalJsFile] = useState(filters.jsFile);
  const debounceBaseRef = useRef(null);
  const debounceJsRef = useRef(null);

  // Sync local state when filters are cleared externally
  useEffect(() => {
    if (!filters.baseUrl && localBaseUrl) setLocalBaseUrl('');
    if (!filters.jsFile && localJsFile) setLocalJsFile('');
  }, [filters.baseUrl, filters.jsFile]);

  const handleBaseUrlChange = (e) => {
    const value = e.target.value;
    setLocalBaseUrl(value);
    if (debounceBaseRef.current) clearTimeout(debounceBaseRef.current);
    debounceBaseRef.current = setTimeout(() => {
      onFilterChange(section, 'baseUrl', value);
    }, 400);
  };

  const handleJsFileChange = (e) => {
    const value = e.target.value;
    setLocalJsFile(value);
    if (debounceJsRef.current) clearTimeout(debounceJsRef.current);
    debounceJsRef.current = setTimeout(() => {
      onFilterChange(section, 'jsFile', value);
    }, 400);
  };

  const handleClear = () => {
    setLocalBaseUrl('');
    setLocalJsFile('');
    if (debounceBaseRef.current) clearTimeout(debounceBaseRef.current);
    if (debounceJsRef.current) clearTimeout(debounceJsRef.current);
    onClearFilters(section);
  };

  return (
    <div className="cyber-card p-3 sm:p-4 mb-3 sm:mb-4">
      <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
        {!hideBaseUrl && (
          <div className="flex items-center gap-2 flex-1">
            <Filter className="w-4 h-4 text-cyber-blue flex-shrink-0" />
            <input
              type="text"
              placeholder="Filter by Base URL..."
              value={localBaseUrl}
              onChange={handleBaseUrlChange}
              className="flex-1 bg-cyber-dark border border-cyber-light rounded px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyber-blue"
            />
          </div>
        )}
        <div className="flex items-center gap-2 flex-1">
          <Filter className="w-4 h-4 text-cyber-green flex-shrink-0" />
          <input
            type="text"
            placeholder="Filter by JS File URL..."
            value={localJsFile}
            onChange={handleJsFileChange}
            className="flex-1 bg-cyber-dark border border-cyber-light rounded px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-cyber-blue"
          />
        </div>
        {((!hideBaseUrl && localBaseUrl) || localJsFile) && (
          <button
            onClick={handleClear}
            className="cyber-button-secondary flex items-center space-x-1.5 px-3 py-1.5 text-sm touch-manipulation"
          >
            <X className="w-4 h-4" />
            <span>Clear</span>
          </button>
        )}
      </div>
    </div>
  );
});

const ScanDetails = () => {
  const { scanId } = useParams();
  const navigate = useNavigate();
  const [scan, setScan] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [showSecretValues, setShowSecretValues] = useState({});
  const [copiedId, setCopiedId] = useState(null);
  const [viewingFile, setViewingFile] = useState(null);
  const [fileContent, setFileContent] = useState('');
  const [loadingFile, setLoadingFile] = useState(false);
  const [exporting, setExporting] = useState(null); // holds the tabId currently exporting
  const [counts, setCounts] = useState(null); // result counts from /counts endpoint
  const filterDebounceRef = useRef(null); // debounce timer for filter changes
  const filtersRef = useRef({}); // always-current filters for use inside interval closures
  const [inputUrls, setInputUrls] = useState(null); // input URLs used for scan
  const [showInputUrls, setShowInputUrls] = useState(false); // toggle input URLs panel
  const [failedDownloads, setFailedDownloads] = useState({ data: [], total: 0, page: 1, totalPages: 1, loaded: false, loading: false });
  const [filesSubTab, setFilesSubTab] = useState('downloaded'); // 'downloaded' or 'failed'
  const [failedFilters, setFailedFilters] = useState({ baseUrl: '', jsFile: '' });
  const failedFilterDebounceRef = useRef(null);
  const failedFiltersRef = useRef({ baseUrl: '', jsFile: '' }); // always-current failedFilters for interval closures
  const [subsSubTab, setSubsSubTab] = useState('active'); // 'active' | 'inactive' | 'unknown'
  const [subdomainCounts, setSubdomainCounts] = useState({ active: 0, inactive: 0, unknown: 0, total: 0, loaded: false });
  const subdomainCountsLoadedRef = useRef(false); // always-current subdomainCounts.loaded for interval closures
  const [urlsSubTab, setUrlsSubTab] = useState('js'); // 'js' | 'crawl'
  const [urlCounts, setUrlCounts] = useState({ crawl: 0, js: 0, total: 0, loaded: false });
  const urlCountsLoadedRef = useRef(false);
  const [emailsSubTab, setEmailsSubTab] = useState('js');
  const [emailCounts, setEmailCounts] = useState({ crawl: 0, js: 0, total: 0, loaded: false });
  const emailCountsLoadedRef = useRef(false);
  const [applinksSubTab, setApplinksSubTab] = useState('js');
  const [appLinkCounts, setAppLinkCounts] = useState({ crawl: 0, js: 0, total: 0, loaded: false });
  const appLinkCountsLoadedRef = useRef(false);
  const [doclinksSubTab, setDoclinksSubTab] = useState('js');
  const [docLinkCounts, setDocLinkCounts] = useState({ crawl: 0, js: 0, total: 0, loaded: false });
  const docLinkCountsLoadedRef = useRef(false);
  const [sociallinksSubTab, setSociallinksSubTab] = useState('js');
  const [socialLinkCounts, setSocialLinkCounts] = useState({ crawl: 0, js: 0, total: 0, loaded: false });
  const socialLinkCountsLoadedRef = useRef(false);
  const [cloudSubTab, setCloudSubTab] = useState('js');
  const [cloudCounts, setCloudCounts] = useState({ crawl: 0, js: 0, total: 0, loaded: false });
  const cloudCountsLoadedRef = useRef(false);
  const [elapsed, setElapsed] = useState(0); // live elapsed seconds for running scans

  // Paginated data store: { [tabId]: { data: [], total: 0, page: 1, totalPages: 1, loaded: false, loading: false } }
  const initialTabState = () => {
    const state = {};
    Object.keys(TAB_API_MAP).forEach(tab => {
      state[tab] = { data: [], total: 0, page: 1, totalPages: 1, loaded: false, loading: false };
    });
    return state;
  };
  const [tabData, setTabData] = useState(initialTabState);

  // Filter states
  const [filters, setFilters] = useState({
    secrets: { baseUrl: '', jsFile: '' },
    endpoints: { baseUrl: '', jsFile: '' },
    cloud: { baseUrl: '', jsFile: '', source: 'js' },
    subdomains: { baseUrl: '', jsFile: '', status: 'active' },
    ips: { baseUrl: '', jsFile: '' },
    emails: { baseUrl: '', jsFile: '', source: 'js' },
    applinks: { baseUrl: '', jsFile: '', source: 'js' },
    doclinks: { baseUrl: '', jsFile: '', source: 'js' },
    sociallinks: { baseUrl: '', jsFile: '', source: 'js' },
    urls: { baseUrl: '', jsFile: '', source: 'js' },
    files: { baseUrl: '', jsFile: '' }
  });

  // Keep refs in sync so interval closures always read the latest values
  filtersRef.current = filters;
  failedFiltersRef.current = failedFilters;
  subdomainCountsLoadedRef.current = subdomainCounts.loaded;
  urlCountsLoadedRef.current = urlCounts.loaded;
  emailCountsLoadedRef.current = emailCounts.loaded;
  appLinkCountsLoadedRef.current = appLinkCounts.loaded;
  docLinkCountsLoadedRef.current = docLinkCounts.loaded;
  socialLinkCountsLoadedRef.current = socialLinkCounts.loaded;
  cloudCountsLoadedRef.current = cloudCounts.loaded;

  // Fetch scan metadata and result counts
  const fetchScanInfo = useCallback(async () => {
    try {
      const [scanData, countsData] = await Promise.all([
        apiService.getScanById(scanId),
        apiService.getScanCounts(scanId)
      ]);
      setScan(scanData);
      setCounts(countsData);
    } catch (error) {
      console.error('Error fetching scan info:', error);
      setScan(null);
    } finally {
      setLoading(false);
    }
  }, [scanId]);

  // Fetch data for a specific tab with server-side filters
  const fetchTabData = useCallback(async (tabId, page = 1, tabFilters = null) => {
    const apiMethod = TAB_API_MAP[tabId];
    if (!apiMethod) return;

    // Use provided filters or current filter state
    const activeFilters = tabFilters || filters[tabId] || {};

    setTabData(prev => ({
      ...prev,
      [tabId]: { ...prev[tabId], loading: true }
    }));

    try {
      const result = await apiService[apiMethod](scanId, page, ITEMS_PER_PAGE, activeFilters);
      setTabData(prev => ({
        ...prev,
        [tabId]: {
          data: result.data || [],
          total: result.total || 0,
          page: result.page || 1,
          totalPages: result.total_pages || 1,
          loaded: true,
          loading: false
        }
      }));
    } catch (error) {
      console.error(`Error fetching ${tabId}:`, error);
      setTabData(prev => ({
        ...prev,
        [tabId]: { ...prev[tabId], data: [], total: 0, loaded: true, loading: false }
      }));
    }
  }, [scanId, filters]);

  // Fetch input URLs
  const fetchInputUrls = useCallback(async () => {
    try {
      const data = await apiService.getInputUrls(scanId);
      setInputUrls(data.urls || []);
    } catch (error) {
      console.error('Error fetching input URLs:', error);
    }
  }, [scanId]);

  // Fetch failed downloads
  const fetchFailedDownloads = useCallback(async (page = 1, activeFilters = null) => {
    setFailedDownloads(prev => ({ ...prev, loading: true }));
    try {
      const filtersToUse = activeFilters || failedFilters;
      const result = await apiService.getFailedDownloads(scanId, page, ITEMS_PER_PAGE, filtersToUse);
      setFailedDownloads({
        data: result.data || [],
        total: result.total || 0,
        page: result.page || 1,
        totalPages: result.total_pages || 1,
        loaded: true,
        loading: false
      });
    } catch (error) {
      console.error('Error fetching failed downloads:', error);
      setFailedDownloads(prev => ({ ...prev, data: [], total: 0, loaded: true, loading: false }));
    }
  }, [scanId, failedFilters]);

  const fetchSubdomainCounts = useCallback(async () => {
    try {
      const data = await apiService.getSubdomainCounts(scanId);
      setSubdomainCounts({ ...data, loaded: true });
    } catch (error) {
      console.error('Error fetching subdomain counts:', error);
    }
  }, [scanId]);

  const switchSubsSubTab = (tab) => {
    setSubsSubTab(tab);
    const newFilters = { ...filters.subdomains, status: tab };
    setFilters(prev => ({ ...prev, subdomains: newFilters }));
    fetchTabData('subdomains', 1, newFilters);
  };

  const fetchURLCounts = useCallback(async () => {
    try {
      const data = await apiService.getURLCounts(scanId);
      setUrlCounts({ ...data, loaded: true });
    } catch (error) {
      console.error('Error fetching URL counts:', error);
    }
  }, [scanId]);

  const switchUrlsSubTab = (tab) => {
    setUrlsSubTab(tab);
    const newFilters = { ...filters.urls, source: tab };
    setFilters(prev => ({ ...prev, urls: newFilters }));
    fetchTabData('urls', 1, newFilters);
  };

  const fetchEmailCounts = useCallback(async () => {
    try {
      const data = await apiService.getEmailCounts(scanId);
      setEmailCounts({ ...data, loaded: true });
    } catch (error) { console.error('Error fetching email counts:', error); }
  }, [scanId]);

  const switchEmailsSubTab = (tab) => {
    setEmailsSubTab(tab);
    const newFilters = { ...filters.emails, source: tab };
    setFilters(prev => ({ ...prev, emails: newFilters }));
    fetchTabData('emails', 1, newFilters);
  };

  const fetchAppLinkCounts = useCallback(async () => {
    try {
      const data = await apiService.getAppLinkCounts(scanId);
      setAppLinkCounts({ ...data, loaded: true });
    } catch (error) { console.error('Error fetching app link counts:', error); }
  }, [scanId]);

  const switchApplinksSubTab = (tab) => {
    setApplinksSubTab(tab);
    const newFilters = { ...filters.applinks, source: tab };
    setFilters(prev => ({ ...prev, applinks: newFilters }));
    fetchTabData('applinks', 1, newFilters);
  };

  const fetchDocLinkCounts = useCallback(async () => {
    try {
      const data = await apiService.getDocLinkCounts(scanId);
      setDocLinkCounts({ ...data, loaded: true });
    } catch (error) { console.error('Error fetching doc link counts:', error); }
  }, [scanId]);

  const switchDoclinksSubTab = (tab) => {
    setDoclinksSubTab(tab);
    const newFilters = { ...filters.doclinks, source: tab };
    setFilters(prev => ({ ...prev, doclinks: newFilters }));
    fetchTabData('doclinks', 1, newFilters);
  };

  const fetchSocialLinkCounts = useCallback(async () => {
    try {
      const data = await apiService.getSocialLinkCounts(scanId);
      setSocialLinkCounts({ ...data, loaded: true });
    } catch (error) { console.error('Error fetching social link counts:', error); }
  }, [scanId]);

  const switchSociallinksSubTab = (tab) => {
    setSociallinksSubTab(tab);
    const newFilters = { ...filters.sociallinks, source: tab };
    setFilters(prev => ({ ...prev, sociallinks: newFilters }));
    fetchTabData('sociallinks', 1, newFilters);
  };

  const fetchCloudCounts = useCallback(async () => {
    try {
      const data = await apiService.getCloudResourceCounts(scanId);
      setCloudCounts({ ...data, loaded: true });
    } catch (error) { console.error('Error fetching cloud counts:', error); }
  }, [scanId]);

  const switchCloudSubTab = (tab) => {
    setCloudSubTab(tab);
    const newFilters = { ...filters.cloud, source: tab };
    setFilters(prev => ({ ...prev, cloud: newFilters }));
    fetchTabData('cloud', 1, newFilters);
  };

  const updateFailedFilter = (section, filterType, value) => {
    const newFilters = { ...failedFilters, [filterType]: value };
    setFailedFilters(newFilters);
    fetchFailedDownloads(1, newFilters);
  };

  const clearFailedFilters = () => {
    const cleared = { baseUrl: '', jsFile: '' };
    setFailedFilters(cleared);
    if (failedFilterDebounceRef.current) clearTimeout(failedFilterDebounceRef.current);
    fetchFailedDownloads(1, cleared);
  };

  const exportFailedCSV = async () => {
    if (exporting) return;
    setExporting('failed');
    try {
      // Fetch all pages
      let allData = [];
      const firstPage = await apiService.getFailedDownloads(scanId, 1, 200, failedFilters);
      allData = firstPage.data || [];
      const totalPages = firstPage.total_pages || 1;
      if (totalPages > 1) {
        const promises = [];
        for (let p = 2; p <= totalPages; p++) {
          promises.push(apiService.getFailedDownloads(scanId, p, 200, failedFilters));
        }
        const results = await Promise.all(promises);
        for (const r of results) allData = allData.concat(r.data || []);
      }
      if (allData.length) {
        const data = allData.map(f => ({ js_url: f.js_url, error: f.error, ...(isFullScan && { baseUrl: f.baseUrl || '' }) }));
        const csv = convertToCSV(data, isFullScan ? ['js_url', 'error', 'baseUrl'] : ['js_url', 'error']);
        downloadCSV(csv, `failed_downloads_${scan.name}_${new Date().toISOString()}.csv`);
      }
    } catch (error) {
      console.error('Error exporting failed downloads:', error);
    } finally {
      setExporting(null);
    }
  };

  // Initial load - just scan info
  useEffect(() => {
    fetchScanInfo();
    fetchInputUrls();
  }, [fetchScanInfo, fetchInputUrls]);

  // Auto-refresh for running scans
  useEffect(() => {
    let intervalId;
    if (scan && (scan.status === 'running' || scan.status === 'pending')) {
      intervalId = setInterval(() => {
        fetchScanInfo();
        // Also refresh active tab if it's loaded (use filtersRef to avoid stale closure)
        if (activeTab !== 'overview' && tabData[activeTab]?.loaded) {
          fetchTabData(activeTab, tabData[activeTab].page, filtersRef.current[activeTab]);
        }
        // Refresh failed downloads if on files tab (use failedFiltersRef to avoid stale closure)
        if (activeTab === 'files' && failedDownloads.loaded) {
          fetchFailedDownloads(failedDownloads.page, failedFiltersRef.current);
        }
        // Refresh subdomain counts if on subdomains tab (use ref to avoid stale closure)
        if (activeTab === 'subdomains' && subdomainCountsLoadedRef.current) {
          fetchSubdomainCounts();
        }
        // Refresh URL counts if on urls tab
        if (activeTab === 'urls' && urlCountsLoadedRef.current) {
          fetchURLCounts();
        }
        if (activeTab === 'emails' && emailCountsLoadedRef.current) {
          fetchEmailCounts();
        }
        if (activeTab === 'applinks' && appLinkCountsLoadedRef.current) {
          fetchAppLinkCounts();
        }
        if (activeTab === 'doclinks' && docLinkCountsLoadedRef.current) {
          fetchDocLinkCounts();
        }
        if (activeTab === 'sociallinks' && socialLinkCountsLoadedRef.current) {
          fetchSocialLinkCounts();
        }
        if (activeTab === 'cloud' && cloudCountsLoadedRef.current) {
          fetchCloudCounts();
        }
      }, 3000);
    }
    return () => {
      if (intervalId) clearInterval(intervalId);
    };
  }, [scan?.status, activeTab]);

  // Live duration timer — ticks every second while scan is running
  useEffect(() => {
    if (!scan || scan.status !== 'running') return;
    const startTime = new Date(scan.started_at || scan.created_at);
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - startTime.getTime()) / 1000)));
    tick(); // set immediately so there's no 1s delay on mount
    const timerId = setInterval(tick, 1000);
    return () => clearInterval(timerId);
  }, [scan?.status, scan?.started_at, scan?.created_at]);

  // Cleanup debounce timers on unmount
  useEffect(() => {
    return () => {
      if (filterDebounceRef.current) clearTimeout(filterDebounceRef.current);
      if (failedFilterDebounceRef.current) clearTimeout(failedFilterDebounceRef.current);
    };
  }, []);

  // Lazy-load tab data when tab changes
  useEffect(() => {
    if (activeTab !== 'overview' && !tabData[activeTab]?.loaded) {
      fetchTabData(activeTab, 1);
    }
    // Load failed downloads when files tab is active
    if (activeTab === 'files' && !failedDownloads.loaded) {
      fetchFailedDownloads(1);
    }
    // Load subdomain counts when subdomains tab is active
    if (activeTab === 'subdomains' && !subdomainCounts.loaded) {
      fetchSubdomainCounts();
    }
    // Load URL counts when urls tab is active
    if (activeTab === 'urls' && !urlCounts.loaded) {
      fetchURLCounts();
    }
    if (activeTab === 'emails' && !emailCounts.loaded) {
      fetchEmailCounts();
    }
    if (activeTab === 'applinks' && !appLinkCounts.loaded) {
      fetchAppLinkCounts();
    }
    if (activeTab === 'doclinks' && !docLinkCounts.loaded) {
      fetchDocLinkCounts();
    }
    if (activeTab === 'sociallinks' && !socialLinkCounts.loaded) {
      fetchSocialLinkCounts();
    }
    if (activeTab === 'cloud' && !cloudCounts.loaded) {
      fetchCloudCounts();
    }
  }, [activeTab, fetchTabData, fetchFailedDownloads, failedDownloads.loaded, fetchSubdomainCounts, subdomainCounts.loaded, fetchURLCounts, urlCounts.loaded, fetchEmailCounts, emailCounts.loaded, fetchAppLinkCounts, appLinkCounts.loaded, fetchDocLinkCounts, docLinkCounts.loaded, fetchSocialLinkCounts, socialLinkCounts.loaded, fetchCloudCounts, cloudCounts.loaded]);

  // Page change handler
  const handlePageChange = (tabId, newPage) => {
    fetchTabData(tabId, newPage);
  };

  const handleStartScan = async () => {
    try {
      await apiService.startScan(scanId);
      fetchScanInfo();
    } catch (error) {
      console.error('Error starting scan:', error);
    }
  };

  const handleStopScan = async () => {
    try {
      await apiService.stopScan(scanId);
      fetchScanInfo();
    } catch (error) {
      console.error('Error stopping scan:', error);
    }
  };

  const handleRefresh = () => {
    fetchScanInfo();
    if (activeTab !== 'overview') {
      fetchTabData(activeTab, tabData[activeTab]?.page || 1, filters[activeTab]);
    }
    if (activeTab === 'subdomains') {
      fetchSubdomainCounts();
    }
    if (activeTab === 'urls') {
      fetchURLCounts();
    }
  };

  const copyToClipboard = (text, id) => {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleSecretVisibility = (secretId) => {
    setShowSecretValues(prev => ({ ...prev, [secretId]: !prev[secretId] }));
  };

  const convertToCSV = (data, headers) => {
    if (!data || data.length === 0) return '';
    const csvHeaders = headers.join(',');
    const csvRows = data.map(row =>
      headers.map(header => {
        const value = row[header] || '';
        const escaped = String(value).replace(/"/g, '""');
        return escaped.includes(',') || escaped.includes('"') ? `"${escaped}"` : escaped;
      }).join(',')
    );
    return [csvHeaders, ...csvRows].join('\n');
  };

  const downloadCSV = (csv, filename) => {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Fetch ALL pages for a given tab to collect complete data for export
  // Fetch ALL pages for a given tab (passes current filters to backend)
  const fetchAllPages = async (tabId) => {
    const apiMethod = TAB_API_MAP[tabId];
    if (!apiMethod) return [];

    const activeFilters = filters[tabId] || {};

    // Fetch first page with max per_page to get total count
    const firstPage = await apiService[apiMethod](scanId, 1, 200, activeFilters);
    let allData = firstPage.data || [];
    const totalPages = firstPage.total_pages || 1;

    if (totalPages > 1) {
      // Fetch remaining pages in parallel
      const pagePromises = [];
      for (let p = 2; p <= totalPages; p++) {
        pagePromises.push(apiService[apiMethod](scanId, p, 200, activeFilters));
      }
      const results = await Promise.all(pagePromises);
      for (const result of results) {
        allData = allData.concat(result.data || []);
      }
    }

    return allData;
  };

  const exportToCSV = async (type) => {
    if (exporting) return;
    setExporting(type);

    try {
      // Fetch all data across all pages
      const allData = await fetchAllPages(type);
      if (!allData.length) {
        setExporting(null);
        return;
      }

      let data, headers, filename;

      switch(type) {
        case 'secrets':
          data = allData.map(s => ({ type: s.type, value: s.value, file: s.file, ...(isFullScan && { baseUrl: getBaseUrl(s.file) }) }));
          headers = isFullScan ? ['type', 'value', 'file', 'baseUrl'] : ['type', 'value', 'file'];
          filename = `secrets_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'endpoints':
          data = allData.map(e => ({ type: e.type, url: e.url, file: e.file, ...(isFullScan && { base: e.base || getBaseUrl(e.file) }) }));
          headers = isFullScan ? ['type', 'url', 'file', 'base'] : ['type', 'url', 'file'];
          filename = `endpoints_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'cloud':
          data = allData.map(c => ({ type: c.type, url: c.url, file: c.file, ...(isFullScan && { baseUrl: getBaseUrl(c.file) }) }));
          headers = isFullScan ? ['type', 'url', 'file', 'baseUrl'] : ['type', 'url', 'file'];
          filename = `cloud_resources_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'subdomains':
          data = allData.map(s => ({ subdomain: s.subdomain, file: s.file, ...(isFullScan && { baseUrl: getBaseUrl(s.file) }), status: s.status || 'unknown' }));
          headers = isFullScan ? ['subdomain', 'file', 'baseUrl', 'status'] : ['subdomain', 'file', 'status'];
          filename = `subdomains_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'ips':
          data = allData.map(i => ({ ip: i.ip, file: i.file, ...(isFullScan && { baseUrl: getBaseUrl(i.file) }) }));
          headers = isFullScan ? ['ip', 'file', 'baseUrl'] : ['ip', 'file'];
          filename = `ips_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'emails':
          data = allData.map(e => ({ email: e.email, file: e.file, ...(isFullScan && { baseUrl: getBaseUrl(e.file) }) }));
          headers = isFullScan ? ['email', 'file', 'baseUrl'] : ['email', 'file'];
          filename = `emails_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'applinks':
          data = allData.map(a => ({ type: a.type, url: a.url, file: a.file, ...(isFullScan && { baseUrl: getBaseUrl(a.file) }) }));
          headers = isFullScan ? ['type', 'url', 'file', 'baseUrl'] : ['type', 'url', 'file'];
          filename = `app_links_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'doclinks':
          data = allData.map(d => ({ type: d.type, url: d.url, file: d.file, ...(isFullScan && { baseUrl: getBaseUrl(d.file) }) }));
          headers = isFullScan ? ['type', 'url', 'file', 'baseUrl'] : ['type', 'url', 'file'];
          filename = `doc_links_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'sociallinks':
          data = allData.map(s => ({ platform: s.type, url: s.url, file: s.file, ...(isFullScan && { baseUrl: s.base || getBaseUrl(s.file) }) }));
          headers = isFullScan ? ['platform', 'url', 'file', 'baseUrl'] : ['platform', 'url', 'file'];
          filename = `social_links_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'urls':
          data = allData.map(u => ({ url: u.url, source: u.source || 'js', file: u.file, ...(isFullScan && { baseUrl: u.base || getBaseUrl(u.file) }) }));
          headers = isFullScan ? ['url', 'source', 'file', 'baseUrl'] : ['url', 'source', 'file'];
          filename = `urls_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        case 'files':
          data = allData.map(f => ({ filename: f.filename, size: f.size, type: f.type, url: f.url || '', ...(isFullScan && { baseUrl: f.baseUrl || '' }), downloaded: f.downloaded }));
          headers = isFullScan ? ['filename', 'size', 'type', 'url', 'baseUrl', 'downloaded'] : ['filename', 'size', 'type', 'url', 'downloaded'];
          filename = `files_${scan.name}_${new Date().toISOString()}.csv`;
          break;
        default:
          setExporting(null);
          return;
      }

      const csv = convertToCSV(data, headers);
      downloadCSV(csv, filename);
    } catch (error) {
      console.error(`Error exporting ${type} to CSV:`, error);
    } finally {
      setExporting(null);
    }
  };

  const viewFile = async (file) => {
    setViewingFile(file);
    setLoadingFile(true);
    setFileContent('');
    try {
      const response = await fetch(`http://${window.location.hostname}:3001/api/scans/${scanId}/files/${encodeURIComponent(file.url)}`);
      const data = await response.json();
      if (response.ok) {
        setFileContent(data.content);
      } else {
        setFileContent(`Error loading file: ${data.error}`);
      }
    } catch (error) {
      setFileContent(`Error loading file: ${error.message}`);
    } finally {
      setLoadingFile(false);
    }
  };

  const closeFileViewer = () => {
    setViewingFile(null);
    setFileContent('');
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical': return 'text-cyber-red bg-cyber-red/20';
      case 'high': return 'text-cyber-yellow bg-cyber-yellow/20';
      case 'medium': return 'text-cyber-blue bg-cyber-blue/20';
      case 'low': return 'text-cyber-green bg-cyber-green/20';
      default: return 'text-gray-400 bg-gray-400/20';
    }
  };

  const getStatusIcon = (status, size = 'w-4 h-4 sm:w-5 sm:h-5') => {
    switch (status) {
      case 'running': return <Clock className={`${size} text-cyber-yellow`} />;
      case 'completed': return <CheckCircle className={`${size} text-cyber-green`} />;
      case 'failed': return <AlertTriangle className={`${size} text-cyber-red`} />;
      default: return <Clock className={`${size} text-gray-400`} />;
    }
  };

  const getScanTypeLabel = (scanType) => SCAN_TYPE_LABELS[scanType] || 'Full';

  // JS URLs and File scans have no Base URL concept — only Full scans do
  const isFullScan = !scan?.scan_type || scan.scan_type === 'full';

  const formatLiveDuration = (seconds) => {
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
  };

  const getBaseUrl = (url) => {
    try {
      const urlObj = new URL(url);
      return `${urlObj.protocol}//${urlObj.host}`;
    } catch {
      const match = url.match(/^(https?:\/\/[^/]+)/);
      return match ? match[1] : null;
    }
  };

  // Filter functions - update state and fetch (debounce is handled in FilterBar)
  const updateFilter = (section, filterType, value) => {
    const newFilters = {
      ...filters,
      [section]: { ...filters[section], [filterType]: value }
    };
    setFilters(newFilters);
    fetchTabData(section, 1, newFilters[section]);
  };

  const clearFilters = (section) => {
    let clearedFilter;
    if (section === 'subdomains') {
      clearedFilter = { baseUrl: '', jsFile: '', status: filters.subdomains.status };
    } else if (['urls', 'emails', 'applinks', 'doclinks', 'sociallinks', 'cloud'].includes(section)) {
      clearedFilter = { baseUrl: '', jsFile: '', source: filters[section].source };
    } else {
      clearedFilter = { baseUrl: '', jsFile: '' };
    }
    setFilters(prev => ({
      ...prev,
      [section]: clearedFilter
    }));

    // Immediately refetch without filters
    if (filterDebounceRef.current) clearTimeout(filterDebounceRef.current);
    fetchTabData(section, 1, clearedFilter);
  };

  // Map tab IDs to count keys from /counts endpoint
  const TAB_COUNT_KEY = {
    secrets: 'secrets',
    endpoints: 'endpoints',
    cloud: 'cloud_resources',
    subdomains: 'subdomains',
    ips: 'ips',
    files: 'files',
    emails: 'emails',
    applinks: 'app_links',
    doclinks: 'doc_links',
    sociallinks: 'social_links',
    urls: 'urls'
  };

  // Tab counts: prefer /counts endpoint, then tabData total if tab was loaded
  const getTabCount = (tabId) => {
    if (counts && TAB_COUNT_KEY[tabId] !== undefined) {
      const val = counts[TAB_COUNT_KEY[tabId]];
      if (val !== undefined && val !== null) return val;
    }
    return tabData[tabId]?.total || 0;
  };

  const tabs = [
    { id: 'overview', label: 'Overview', shortLabel: 'Overview', icon: Shield },
    { id: 'secrets', label: 'Secrets', shortLabel: 'Secrets', icon: Key, count: getTabCount('secrets') },
    { id: 'endpoints', label: 'Endpoints', shortLabel: 'Endpoints', icon: Code, count: getTabCount('endpoints') },
    { id: 'cloud', label: 'Cloud', shortLabel: 'Cloud', icon: Cloud, count: getTabCount('cloud') },
    { id: 'subdomains', label: 'Subdomains', shortLabel: 'Subs', icon: Globe, count: getTabCount('subdomains') },
    { id: 'ips', label: 'IPs', shortLabel: 'IPs', icon: Server, count: getTabCount('ips') },
    { id: 'emails', label: 'Emails', shortLabel: 'Emails', icon: Mail, count: getTabCount('emails') },
    { id: 'applinks', label: 'Apps', shortLabel: 'Apps', icon: Smartphone, count: getTabCount('applinks') },
    { id: 'doclinks', label: 'Docs', shortLabel: 'Docs', icon: BookOpen, count: getTabCount('doclinks') },
    { id: 'sociallinks', label: 'Social', shortLabel: 'Social', icon: Share2, count: getTabCount('sociallinks') },
    { id: 'urls', label: 'URLs', shortLabel: 'URLs', icon: Link2, count: getTabCount('urls') },
    { id: 'files', label: 'JS Files', shortLabel: 'JS Files', icon: Download, count: getTabCount('files') }
  ];

  // Stat Card Component
  const StatCard = ({ label, value, icon: Icon, color, border }) => (
    <div className={`cyber-card p-3 sm:p-4 lg:p-5 ${border ? `border-${border}/50` : ''}`}>
      <div className="flex items-center justify-between">
        <div className="min-w-0">
          <p className="text-gray-400 text-xs sm:text-sm truncate">{label}</p>
          <p className={`text-lg sm:text-xl lg:text-2xl font-bold ${color || 'text-white'}`}>{value}</p>
        </div>
        {Icon && <Icon className={`w-5 h-5 sm:w-6 sm:h-6 flex-shrink-0 ${color || 'text-gray-400'}`} />}
      </div>
    </div>
  );

  // Source Sub-Tabs Component (JS Files / Crawl Results)
  // Full scans only: filter tabs on left, ItemCount + ExportButton on right.
  // Non-full scans (JS URLs / File): return null — SectionHeader owns count + export.
  const SourceSubTabs = ({ activeSubTab, onSwitch, counts, jsColor = 'cyber-purple', crawlColor = 'cyber-blue', tabId }) => {
    if (!isFullScan) return null;
    return (
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex flex-wrap items-center gap-1 justify-start self-start bg-cyber-gray rounded-lg p-1">
          <button
            onClick={() => onSwitch('js')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium transition-colors touch-manipulation whitespace-nowrap ${
              activeSubTab === 'js'
                ? `bg-${jsColor}/20 text-${jsColor}`
                : 'text-gray-400 hover:text-white hover:bg-cyber-light'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>From JS Files</span>
            <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
              activeSubTab === 'js' ? `bg-${jsColor}/20 text-${jsColor}` : 'bg-cyber-light text-gray-400'
            }`}>{counts.js}</span>
          </button>
          <button
            onClick={() => onSwitch('crawl')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs sm:text-sm font-medium transition-colors touch-manipulation whitespace-nowrap ${
              activeSubTab === 'crawl'
                ? `bg-${crawlColor}/20 text-${crawlColor}`
                : 'text-gray-400 hover:text-white hover:bg-cyber-light'
            }`}
          >
            <Globe className="w-3.5 h-3.5" />
            <span>From Crawl Results</span>
            <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
              activeSubTab === 'crawl' ? `bg-${crawlColor}/20 text-${crawlColor}` : 'bg-cyber-light text-gray-400'
            }`}>{counts.crawl}</span>
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          <ItemCount tabId={tabId} />
          <ExportButton tabId={tabId} />
        </div>
      </div>
    );
  };

  const SubdomainSubTabs = ({ activeSubTab, onSwitch, counts, tabId }) => (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <div className="flex flex-wrap items-center gap-1 justify-start self-start bg-cyber-gray rounded-lg p-1">
        <button
          onClick={() => onSwitch('active')}
          className={`flex min-w-max items-center space-x-1.5 rounded-md px-3 py-1.5 text-xs sm:text-sm font-medium transition-colors touch-manipulation whitespace-nowrap ${
            activeSubTab === 'active'
              ? 'bg-cyber-green/20 text-cyber-green'
              : 'text-gray-400 hover:text-white hover:bg-cyber-light'
          }`}
        >
          <CheckCircle className="w-3.5 h-3.5" />
          <span>Active</span>
          <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
            activeSubTab === 'active' ? 'bg-cyber-green/20 text-cyber-green' : 'bg-cyber-light text-gray-400'
          }`}>{counts.active}</span>
        </button>
        <button
          onClick={() => onSwitch('inactive')}
          className={`flex min-w-max items-center space-x-1.5 rounded-md px-3 py-1.5 text-xs sm:text-sm font-medium transition-colors touch-manipulation whitespace-nowrap ${
            activeSubTab === 'inactive'
              ? 'bg-cyber-red/20 text-cyber-red'
              : 'text-gray-400 hover:text-white hover:bg-cyber-light'
          }`}
        >
          <XCircle className="w-3.5 h-3.5" />
          <span>Inactive</span>
          <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
            activeSubTab === 'inactive' ? 'bg-cyber-red/20 text-cyber-red' : 'bg-cyber-light text-gray-400'
          }`}>{counts.inactive}</span>
        </button>
        <button
          onClick={() => onSwitch('unknown')}
          className={`flex min-w-max items-center space-x-1.5 rounded-md px-3 py-1.5 text-xs sm:text-sm font-medium transition-colors touch-manipulation whitespace-nowrap ${
            activeSubTab === 'unknown'
              ? 'bg-yellow-500/20 text-yellow-400'
              : 'text-gray-400 hover:text-white hover:bg-cyber-light'
          }`}
        >
          <HelpCircle className="w-3.5 h-3.5" />
          <span>Unknown</span>
          <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
            activeSubTab === 'unknown' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-cyber-light text-gray-400'
          }`}>{counts.unknown}</span>
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <ItemCount tabId={tabId} />
        <ExportButton tabId={tabId} />
      </div>
    </div>
  );

  const FilesSubTabs = ({ activeSubTab, onSwitch, counts, exporting, onExportFailed }) => (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      <div className="flex flex-wrap items-center gap-1 justify-start self-start bg-cyber-gray rounded-lg p-1">
        <button
          onClick={() => onSwitch('downloaded')}
          className={`flex min-w-max items-center space-x-1.5 rounded-md px-3 py-1.5 text-xs sm:text-sm font-medium transition-colors touch-manipulation whitespace-nowrap ${
            activeSubTab === 'downloaded'
              ? 'bg-cyber-green/20 text-cyber-green'
              : 'text-gray-400 hover:text-white hover:bg-cyber-light'
          }`}
        >
          <CheckCircle className="w-3.5 h-3.5" />
          <span>Downloaded</span>
          <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
            activeSubTab === 'downloaded' ? 'bg-cyber-green/20 text-cyber-green' : 'bg-cyber-light text-gray-400'
          }`}>{counts.downloaded}</span>
        </button>
        <button
          onClick={() => onSwitch('failed')}
          className={`flex min-w-max items-center space-x-1.5 rounded-md px-3 py-1.5 text-xs sm:text-sm font-medium transition-colors touch-manipulation whitespace-nowrap ${
            activeSubTab === 'failed'
              ? 'bg-cyber-red/20 text-cyber-red'
              : 'text-gray-400 hover:text-white hover:bg-cyber-light'
          }`}
        >
          <AlertTriangle className="w-3.5 h-3.5" />
          <span>Failed</span>
          <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${
            activeSubTab === 'failed' ? 'bg-cyber-red/20 text-cyber-red' : 'bg-cyber-light text-gray-400'
          }`}>{counts.failed}</span>
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        {activeSubTab === 'downloaded' ? (
          <>
            <ItemCount tabId="files" />
            <ExportButton tabId="files" />
          </>
        ) : (
          activeSubTab === 'failed' && counts.failed > 0 && (
            <>
              <span className="text-gray-400 text-sm">{counts.failed} items</span>
              <button
                onClick={onExportFailed}
                disabled={exporting === 'failed'}
                className="cyber-button-secondary flex items-center space-x-1.5 text-xs sm:text-sm py-1.5 px-2.5 sm:px-3 touch-manipulation disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {exporting === 'failed' ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 sm:w-4 sm:h-4 animate-spin" />
                    <span>Exporting...</span>
                  </>
                ) : (
                  <>
                    <Download className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                    <span>Export Failed CSV</span>
                  </>
                )}
              </button>
            </>
          )
        )}
      </div>
    </div>
  );

  // Item Card Component
  const ItemCard = ({ icon: Icon, iconColor, title, subtitle, badge, badgeColor, actions, children, borderColor, baseUrl }) => (
    <div className={`cyber-card p-3 sm:p-4 ${borderColor ? `border-${borderColor}/30` : ''}`}>
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 sm:gap-4">
        <div className="flex items-start space-x-2 sm:space-x-3 min-w-0 flex-1">
          <Icon className={`w-4 h-4 flex-shrink-0 mt-0.5 ${iconColor}`} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5 sm:gap-2 mb-1">
              {badge && (
                <span className={`px-1.5 sm:px-2 py-0.5 sm:py-1 rounded text-[10px] sm:text-xs ${badgeColor}`}>
                  {badge}
                </span>
              )}
              <span className="font-mono text-white text-xs sm:text-sm break-all">{title}</span>
            </div>
            {baseUrl && (
              <div className="mb-1">
                <span className="text-gray-400 text-xs">Base URL: </span>
                <span className="text-gray-300 text-xs font-mono">{baseUrl}</span>
              </div>
            )}
            {subtitle && <p className="text-gray-400 text-xs truncate">{subtitle}</p>}
            {children}
          </div>
        </div>
        {actions && (
          <div className="flex items-center space-x-1 flex-shrink-0 self-end sm:self-start">
            {actions}
          </div>
        )}
      </div>
    </div>
  );

  // Pagination Component
  const Pagination = ({ tabId }) => {
    const tab = tabData[tabId];
    if (!tab || tab.totalPages <= 1) return null;

    const { page, totalPages, total } = tab;
    const start = (page - 1) * ITEMS_PER_PAGE + 1;
    const end = Math.min(page * ITEMS_PER_PAGE, total);

    // Generate page numbers to show
    const getPageNumbers = () => {
      const pages = [];
      const maxVisible = 5;
      let startPage = Math.max(1, page - Math.floor(maxVisible / 2));
      let endPage = Math.min(totalPages, startPage + maxVisible - 1);
      if (endPage - startPage + 1 < maxVisible) {
        startPage = Math.max(1, endPage - maxVisible + 1);
      }
      for (let i = startPage; i <= endPage; i++) {
        pages.push(i);
      }
      return pages;
    };

    return (
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mt-4 pt-4 border-t border-cyber-light">
        <span className="text-gray-400 text-sm">
          Showing {start}-{end} of {total} items
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => handlePageChange(tabId, 1)}
            disabled={page === 1}
            className="p-1.5 rounded hover:bg-cyber-light disabled:opacity-30 disabled:cursor-not-allowed transition-colors touch-manipulation"
          >
            <ChevronsLeft className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={() => handlePageChange(tabId, page - 1)}
            disabled={page === 1}
            className="p-1.5 rounded hover:bg-cyber-light disabled:opacity-30 disabled:cursor-not-allowed transition-colors touch-manipulation"
          >
            <ChevronLeft className="w-4 h-4 text-gray-400" />
          </button>

          {getPageNumbers().map(pageNum => (
            <button
              key={pageNum}
              onClick={() => handlePageChange(tabId, pageNum)}
              className={`min-w-[32px] h-8 rounded text-sm font-medium transition-colors touch-manipulation ${
                pageNum === page
                  ? 'bg-cyber-blue text-cyber-dark'
                  : 'text-gray-400 hover:bg-cyber-light hover:text-white'
              }`}
            >
              {pageNum}
            </button>
          ))}

          <button
            onClick={() => handlePageChange(tabId, page + 1)}
            disabled={page === totalPages}
            className="p-1.5 rounded hover:bg-cyber-light disabled:opacity-30 disabled:cursor-not-allowed transition-colors touch-manipulation"
          >
            <ChevronRight className="w-4 h-4 text-gray-400" />
          </button>
          <button
            onClick={() => handlePageChange(tabId, totalPages)}
            disabled={page === totalPages}
            className="p-1.5 rounded hover:bg-cyber-light disabled:opacity-30 disabled:cursor-not-allowed transition-colors touch-manipulation"
          >
            <ChevronsRight className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>
    );
  };

  // Tab loading spinner
  const TabLoading = () => (
    <div className="flex items-center justify-center py-12">
      <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-cyber-blue"></div>
    </div>
  );

  // Get tab data (server already filtered and paginated)
  const getTabItems = (tabId) => {
    const tab = tabData[tabId];
    if (!tab || !tab.data) return [];
    return tab.data;
  };

  // Check if filters are active for a tab
  const hasActiveFilters = (tabId) => {
    const f = filters[tabId];
    return f && (f.baseUrl || f.jsFile);
  };

  // Export button component
  const ExportButton = ({ tabId }) => {
    const tab = tabData[tabId];
    const totalCount = tab?.total || 0;
    if (totalCount <= 0) return null;
    return (
      <button
        onClick={() => exportToCSV(tabId)}
        disabled={exporting === tabId}
        className="cyber-button-secondary flex items-center space-x-1.5 text-xs sm:text-sm py-1.5 px-2.5 sm:px-3 touch-manipulation disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {exporting === tabId ? (
          <>
            <RefreshCw className="w-3.5 h-3.5 sm:w-4 sm:h-4 animate-spin" />
            <span>Exporting...</span>
          </>
        ) : (
          <>
            <Download className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
            <span>Export All as CSV</span>
          </>
        )}
      </button>
    );
  };

  // Item count display
  const ItemCount = ({ tabId }) => {
    const tab = tabData[tabId];
    const pageCount = tab?.data?.length || 0;
    const totalCount = tab?.total || 0;
    const totalUnfiltered = getTabCount(tabId);
    const isFiltered = hasActiveFilters(tabId);
    return (
      <span className="text-gray-400 text-sm">
        {isFiltered
          ? `${totalCount} matched / ${totalUnfiltered} total`
          : `${pageCount} of ${totalCount} items`
        }
      </span>
    );
  };

  // Section header with count and export
  const SectionHeader = ({ title, tabId, hideExport }) => {
    return (
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-3">
        <h2 className="text-lg sm:text-xl font-semibold text-white">{title}</h2>
        {!hideExport && (
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <ItemCount tabId={tabId} />
            <ExportButton tabId={tabId} />
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex-1 p-4 sm:p-6 lg:p-8">
        <div className="flex items-center justify-center h-full">
          <div className="animate-spin rounded-full h-10 w-10 sm:h-12 sm:w-12 border-b-2 border-cyber-blue"></div>
        </div>
      </div>
    );
  }

  if (!scan) {
    return (
      <div className="flex-1 p-4 sm:p-6 lg:p-8">
        <div className="text-center py-12">
          <AlertTriangle className="w-12 h-12 sm:w-16 sm:h-16 text-cyber-red mx-auto mb-4" />
          <h3 className="text-lg sm:text-xl font-semibold text-white mb-2">Scan Not Found</h3>
          <p className="text-gray-400 mb-6 text-sm sm:text-base">The requested scan could not be found.</p>
          <button onClick={() => navigate('/scans')} className="cyber-button-primary">
            Back to Scans
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col min-h-screen">
      {/* Header */}
      <div className="p-4 sm:p-6 lg:p-8 border-b border-cyber-light pt-14 lg:pt-6 bg-cyber-gray/80 backdrop-blur-xl">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center space-x-3 sm:space-x-4 min-w-0 flex-1">
            <button
              onClick={() => navigate('/scans')}
              className="p-2 hover:bg-cyber-light rounded-lg transition-colors flex-shrink-0 touch-manipulation"
            >
              <ArrowLeft className="w-5 h-5 text-gray-400" />
            </button>
            <div className="min-w-0 flex-1">
              <div className="flex items-center space-x-2 sm:space-x-3 mb-1">
                {getStatusIcon(scan.status)}
                <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold text-white truncate tracking-tight">
                  {scan.name}
                </h1>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] sm:text-xs bg-cyber-blue/20 text-cyber-blue border border-cyber-blue/30 flex-shrink-0">
                  {getScanTypeLabel(scan.scan_type)}
                </span>
              </div>
              <button
                onClick={() => setShowInputUrls(!showInputUrls)}
                className="text-gray-400 font-mono text-xs sm:text-sm hover:text-cyber-blue transition-colors flex items-center gap-1.5"
              >
                <Globe className="w-3 h-3 flex-shrink-0" />
                <span>{inputUrls ? `${inputUrls.length} URL(s)` : 'Loading...'}</span>
                <span className="text-[10px]">{showInputUrls ? '▲' : '▼'}</span>
              </button>
            </div>
          </div>
          <div className="flex items-center space-x-2 sm:space-x-3 flex-shrink-0 self-end sm:self-auto">
            <button
              onClick={handleRefresh}
              className="cyber-button-secondary flex items-center space-x-1.5 sm:space-x-2 text-xs sm:text-sm py-1.5 sm:py-2 px-2.5 sm:px-4 touch-manipulation"
            >
              <RefreshCw className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
              <span className="hidden sm:inline">Refresh</span>
            </button>
            {scan.status === 'pending' && (
              <button
                onClick={handleStartScan}
                className="cyber-button-primary flex items-center space-x-1.5 sm:space-x-2 text-xs sm:text-sm py-1.5 sm:py-2 px-2.5 sm:px-4 touch-manipulation"
              >
                <Play className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                <span>Start</span>
              </button>
            )}
            {scan.status === 'running' && (
              <button
                onClick={handleStopScan}
                className="cyber-button-secondary flex items-center space-x-1.5 sm:space-x-2 text-xs sm:text-sm py-1.5 sm:py-2 px-2.5 sm:px-4 touch-manipulation"
              >
                <Pause className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                <span>Stop</span>
              </button>
            )}
          </div>
        </div>

        {/* Expandable Input URLs Panel */}
        {showInputUrls && inputUrls && (
          <div className="mt-3 ml-11 sm:ml-14 cyber-card p-3 sm:p-4 border-cyber-blue/30">
            <div className="flex items-center justify-between mb-2">
              <p className="text-gray-400 text-xs uppercase tracking-wider font-medium">Input URLs ({inputUrls.length})</p>
              <button
                onClick={() => copyToClipboard(inputUrls.join('\n'), 'input-urls')}
                className="p-1.5 hover:bg-cyber-light rounded transition-colors touch-manipulation"
              >
                {copiedId === 'input-urls' ? <CheckCircle className="w-3.5 h-3.5 text-cyber-green" /> : <Copy className="w-3.5 h-3.5 text-gray-400" />}
              </button>
            </div>
            <div className="max-h-40 overflow-y-auto scrollbar-thin space-y-1">
              {inputUrls.map((url, idx) => (
                <div key={idx} className="flex items-center gap-2 group">
                  <span className="text-gray-500 text-[10px] w-5 text-right flex-shrink-0">{idx + 1}</span>
                  <a
                    href={url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-mono text-xs text-cyber-blue hover:text-cyber-blue/80 truncate"
                  >
                    {url}
                  </a>
                  <ExternalLink className="w-3 h-3 text-gray-500 opacity-0 group-hover:opacity-100 flex-shrink-0 transition-opacity" />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Sidebar + Content Layout */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Left Sidebar Navigation */}
        <div className="w-full lg:w-56 flex-shrink-0 border-b lg:border-b-0 lg:border-r border-cyber-light bg-cyber-gray/60 overflow-x-auto lg:overflow-y-auto scrollbar-thin">
          <div className="py-2 flex lg:block min-w-max lg:min-w-0">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-auto lg:w-full flex items-center justify-between gap-2 px-3 sm:px-4 py-2.5 transition-all duration-200 touch-manipulation whitespace-nowrap ${
                    activeTab === tab.id
                      ? 'bg-cyber-blue/10 text-cyber-blue border-b-2 lg:border-b-0 lg:border-r-2 border-cyber-blue'
                      : 'text-gray-400 hover:bg-cyber-light hover:text-white'
                  }`}
                >
                  <div className="flex items-center space-x-2.5 min-w-0">
                    <Icon className="w-4 h-4 flex-shrink-0" />
                    <span className="text-sm truncate">{tab.label}</span>
                  </div>
                  {tab.count !== undefined && tab.count > 0 && (
                    <span className={`px-1.5 py-0.5 rounded-full text-[10px] flex-shrink-0 ${
                      activeTab === tab.id ? 'bg-cyber-blue/20 text-cyber-blue' : 'bg-cyber-light text-gray-500'
                    }`}>
                      {tab.count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 p-3 sm:p-6 lg:p-8 overflow-auto scrollbar-thin">
        {activeTab === 'overview' && (
          <div className="space-y-4 sm:space-y-6">
            {/* Scan Info */}
            <div className="cyber-card p-3 sm:p-4 lg:p-5">
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
                <div className="flex items-center space-x-2.5">
                  {getStatusIcon(scan.status, 'w-4 h-4 sm:w-5 sm:h-5')}
                  <div>
                    <p className="text-gray-400 text-[10px] sm:text-xs uppercase tracking-wider">Status</p>
                    <p className="text-white text-sm sm:text-base font-semibold capitalize">{scan.status}</p>
                  </div>
                </div>
                <div className="flex items-center space-x-2.5">
                  <Clock className="w-4 h-4 sm:w-5 sm:h-5 text-gray-400 flex-shrink-0" />
                  <div>
                    <p className="text-gray-400 text-[10px] sm:text-xs uppercase tracking-wider">Created</p>
                    <p className="text-white text-sm sm:text-base font-semibold">{new Date(scan.created_at).toLocaleDateString()}</p>
                  </div>
                </div>
                <div className="flex items-center space-x-2.5">
                  <Clock className="w-4 h-4 sm:w-5 sm:h-5 text-gray-400 flex-shrink-0" />
                  <div>
                    <p className="text-gray-400 text-[10px] sm:text-xs uppercase tracking-wider">Duration</p>
                    <p className="text-white text-sm sm:text-base font-semibold">
                      {scan.completed_at
                        ? `${Math.round((new Date(scan.completed_at) - new Date(scan.created_at)) / 60000)}m`
                        : scan.status === 'running'
                          ? formatLiveDuration(elapsed)
                          : 'Pending...'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center space-x-2.5">
                  <HardDrive className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-yellow flex-shrink-0" />
                  <div>
                    <p className="text-gray-400 text-[10px] sm:text-xs uppercase tracking-wider">Storage</p>
                    <p className="text-white text-sm sm:text-base font-semibold">{scan.storage_mb >= 1024 ? `${(scan.storage_mb / 1024).toFixed(1)} GB` : `${(scan.storage_mb || 0).toFixed(1)} MB`}</p>
                  </div>
                </div>
                <div className="flex items-center space-x-2.5">
                  <Cpu className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-purple flex-shrink-0" />
                  <div>
                    <p className="text-gray-400 text-[10px] sm:text-xs uppercase tracking-wider">
                      {scan.status === 'running' && scan.current_ram_mb != null ? 'RAM (Live)' : 'Peak RAM'}
                    </p>
                    <p className="text-white text-sm sm:text-base font-semibold">
                      {scan.status === 'running' && scan.current_ram_mb != null
                        ? (scan.current_ram_mb >= 1024 ? `${(scan.current_ram_mb / 1024).toFixed(1)} GB` : `${scan.current_ram_mb.toFixed(1)} MB`)
                        : (scan.peak_ram_mb >= 1024 ? `${(scan.peak_ram_mb / 1024).toFixed(1)} GB` : `${(scan.peak_ram_mb || 0).toFixed(1)} MB`)
                      }
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Result Stats */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-4 lg:gap-5">
              <StatCard label="Secrets" value={getTabCount('secrets')} icon={Key} color="text-cyber-red" border="cyber-red" />
              <StatCard label="Endpoints" value={getTabCount('endpoints')} icon={Code} color="text-cyber-blue" border="cyber-blue" />
              <StatCard label="Cloud" value={getTabCount('cloud')} icon={Cloud} color="text-cyber-purple" border="cyber-purple" />
              <StatCard label="Subdomains" value={getTabCount('subdomains')} icon={Globe} color="text-cyber-green" border="cyber-green" />
              <StatCard label="IPs" value={getTabCount('ips')} icon={Server} color="text-cyber-yellow" border="cyber-yellow" />
              <StatCard label="Emails" value={getTabCount('emails')} icon={Mail} color="text-cyber-blue" border="cyber-blue" />
              <StatCard label="App Links" value={getTabCount('applinks')} icon={Smartphone} color="text-cyber-green" border="cyber-green" />
              <StatCard label="Doc Links" value={getTabCount('doclinks')} icon={BookOpen} color="text-cyber-yellow" border="cyber-yellow" />
              <StatCard label="Social" value={getTabCount('sociallinks')} icon={Share2} color="text-cyber-red" border="cyber-red" />
              <StatCard label="URLs" value={getTabCount('urls')} icon={Link2} color="text-cyber-purple" border="cyber-purple" />
              <StatCard label="JS Files" value={getTabCount('files')} icon={Download} color="text-cyber-blue" border="cyber-blue" />
            </div>
          </div>
        )}

        {activeTab === 'secrets' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="Secrets Found" tabId="secrets" />
            {(tabData.secrets.loaded || hasActiveFilters('secrets')) && (
              <FilterBar section="secrets" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.secrets} hideBaseUrl={!isFullScan} />
            )}
            {tabData.secrets.loading ? <TabLoading /> : (
              <>
                {tabData.secrets.total > 0 ? getTabItems('secrets').map((secret) => (
                  <ItemCard
                    key={secret.id}
                    icon={Key}
                    iconColor="text-cyber-red"
                    badge={secret.type}
                    badgeColor="bg-cyber-red/20 text-cyber-red"
                    title={showSecretValues[secret.id] ? secret.value : '••••••••••••••••'}
                    subtitle={`Found in ${secret.file}`}
                    baseUrl={isFullScan ? (secret.base || getBaseUrl(secret.file)) : undefined}
                    borderColor="cyber-red"
                    actions={
                      <>
                        <button onClick={() => toggleSecretVisibility(secret.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          {showSecretValues[secret.id] ? <EyeOff className="w-4 h-4 text-gray-400" /> : <Eye className="w-4 h-4 text-gray-400" />}
                        </button>
                        <button onClick={() => copyToClipboard(secret.value, secret.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          {copiedId === secret.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                        </button>
                      </>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <Key className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('secrets') ? 'No secrets match your filters' : 'No secrets found in this scan'}
                    </p>
                  </div>
                )}
                <Pagination tabId="secrets" />
              </>
            )}
          </div>
        )}

        {activeTab === 'endpoints' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="API Endpoints" tabId="endpoints" />
            {(tabData.endpoints.loaded || hasActiveFilters('endpoints')) && (
              <FilterBar section="endpoints" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.endpoints} hideBaseUrl={!isFullScan} />
            )}
            {tabData.endpoints.loading ? <TabLoading /> : (
              <>
                {tabData.endpoints.total > 0 ? getTabItems('endpoints').map((endpoint) => (
                  <ItemCard
                    key={endpoint.id}
                    icon={Globe}
                    iconColor="text-cyber-blue"
                    badge={endpoint.type}
                    badgeColor={
                      endpoint.type === 'Endpoint' ? 'bg-cyber-green/20 text-cyber-green font-mono' :
                      endpoint.type === 'Parameter' ? 'bg-cyber-yellow/20 text-cyber-yellow font-mono' :
                      'bg-cyber-blue/20 text-cyber-blue font-mono'
                    }
                    title={endpoint.url}
                    subtitle={`Found in ${endpoint.file}`}
                    baseUrl={isFullScan ? (endpoint.base || getBaseUrl(endpoint.file)) : undefined}
                    actions={
                      <button onClick={() => copyToClipboard(endpoint.url, endpoint.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                        {copiedId === endpoint.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                      </button>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <Globe className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('endpoints') ? 'No endpoints match your filters' : 'No endpoints found in this scan'}
                    </p>
                  </div>
                )}
                <Pagination tabId="endpoints" />
              </>
            )}
          </div>
        )}

        {activeTab === 'cloud' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="Cloud Resources" tabId="cloud" hideExport={isFullScan} />
            <SourceSubTabs activeSubTab={cloudSubTab} onSwitch={switchCloudSubTab} counts={cloudCounts} jsColor="cyber-purple" crawlColor="cyber-blue" tabId="cloud" />
            {(tabData.cloud.loaded || hasActiveFilters('cloud')) && (
              <FilterBar section="cloud" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.cloud} hideBaseUrl={!isFullScan} />
            )}
            {tabData.cloud.loading ? <TabLoading /> : (
              <>
                {tabData.cloud.total > 0 ? getTabItems('cloud').map((resource) => (
                  <ItemCard
                    key={resource.id}
                    icon={Cloud}
                    iconColor={cloudSubTab === 'crawl' ? 'text-cyber-blue' : 'text-cyber-purple'}
                    badge={resource.type}
                    badgeColor={cloudSubTab === 'crawl' ? 'bg-cyber-blue/20 text-cyber-blue' : 'bg-cyber-purple/20 text-cyber-purple'}
                    title={resource.url}
                    subtitle={cloudSubTab === 'crawl' ? `Source: crawl` : `Found in ${resource.file}`}
                    baseUrl={isFullScan ? (resource.base || getBaseUrl(resource.file)) : undefined}
                    borderColor={cloudSubTab === 'crawl' ? 'cyber-blue' : 'cyber-purple'}
                    actions={
                      <button onClick={() => copyToClipboard(resource.url, resource.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                        {copiedId === resource.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                      </button>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <Cloud className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('cloud') ? 'No cloud resources match your filters' : `No cloud resources found in ${cloudSubTab === 'crawl' ? 'crawl results' : 'JS files'} during this scan`}
                    </p>
                  </div>
                )}
                <Pagination tabId="cloud" />
              </>
            )}
          </div>
        )}

        {activeTab === 'subdomains' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="Subdomains" tabId="subdomains" hideExport />
            <SubdomainSubTabs
              activeSubTab={subsSubTab}
              onSwitch={switchSubsSubTab}
              counts={subdomainCounts}
              tabId="subdomains"
            />

            {(tabData.subdomains.loaded || hasActiveFilters('subdomains')) && (
              <FilterBar section="subdomains" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.subdomains} hideBaseUrl={!isFullScan} />
            )}
            {tabData.subdomains.loading ? <TabLoading /> : (
              <>
                {tabData.subdomains.total > 0 ? getTabItems('subdomains').map((subdomain) => (
                  <ItemCard
                    key={subdomain.id}
                    icon={Server}
                    iconColor={subsSubTab === 'active' ? 'text-cyber-green' : subsSubTab === 'inactive' ? 'text-cyber-red' : 'text-yellow-400'}
                    title={subdomain.subdomain}
                    subtitle={`Found in ${subdomain.file}`}
                    baseUrl={isFullScan ? (subdomain.base || getBaseUrl(subdomain.file)) : undefined}
                    actions={
                      <button onClick={() => copyToClipboard(subdomain.subdomain, subdomain.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                        {copiedId === subdomain.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                      </button>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <Server className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('subdomains')
                        ? 'No subdomains match your filters'
                        : `No ${subsSubTab} subdomains found in this scan`}
                    </p>
                  </div>
                )}
                <Pagination tabId="subdomains" />
              </>
            )}
          </div>
        )}

        {activeTab === 'ips' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="IP Addresses" tabId="ips" />
            {(tabData.ips.loaded || hasActiveFilters('ips')) && (
              <FilterBar section="ips" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.ips} hideBaseUrl={!isFullScan} />
            )}
            {tabData.ips.loading ? <TabLoading /> : (
              <>
                {tabData.ips.total > 0 ? getTabItems('ips').map((ip) => (
                  <ItemCard
                    key={ip.id}
                    icon={Server}
                    iconColor="text-cyber-yellow"
                    title={ip.ip}
                    subtitle={`Found in ${ip.file}`}
                    baseUrl={isFullScan ? (ip.base || getBaseUrl(ip.file)) : undefined}
                    actions={
                      <button onClick={() => copyToClipboard(ip.ip, ip.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                        {copiedId === ip.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                      </button>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <Server className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('ips') ? 'No IP addresses match your filters' : 'No IP addresses found in this scan'}
                    </p>
                  </div>
                )}
                <Pagination tabId="ips" />
              </>
            )}
          </div>
        )}

        {activeTab === 'emails' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="Emails" tabId="emails" hideExport={isFullScan} />
            <SourceSubTabs activeSubTab={emailsSubTab} onSwitch={switchEmailsSubTab} counts={emailCounts} jsColor="cyber-blue" crawlColor="cyber-blue" tabId="emails" />
            {(tabData.emails.loaded || hasActiveFilters('emails')) && (
              <FilterBar section="emails" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.emails} hideBaseUrl={!isFullScan} />
            )}
            {tabData.emails.loading ? <TabLoading /> : (
              <>
                {tabData.emails.total > 0 ? getTabItems('emails').map((email) => (
                  <ItemCard
                    key={email.id}
                    icon={Mail}
                    iconColor={emailsSubTab === 'crawl' ? 'text-cyber-blue' : 'text-cyber-blue'}
                    title={email.email}
                    subtitle={emailsSubTab === 'crawl' ? `Source: crawl` : `Found in ${email.file}`}
                    baseUrl={isFullScan ? (email.base || getBaseUrl(email.file)) : undefined}
                    borderColor="cyber-blue"
                    actions={
                      <>
                        <button onClick={() => copyToClipboard(email.email, email.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          {copiedId === email.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                        </button>
                        <a href={`mailto:${email.email}`} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          <ExternalLink className="w-4 h-4 text-gray-400" />
                        </a>
                      </>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <Mail className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('emails') ? 'No emails match your filters' : `No emails found in ${emailsSubTab === 'crawl' ? 'crawl results' : 'JS files'} during this scan`}
                    </p>
                  </div>
                )}
                <Pagination tabId="emails" />
              </>
            )}
          </div>
        )}

        {activeTab === 'applinks' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="App Store Links" tabId="applinks" hideExport={isFullScan} />
            <SourceSubTabs activeSubTab={applinksSubTab} onSwitch={switchApplinksSubTab} counts={appLinkCounts} jsColor="cyber-green" crawlColor="cyber-blue" tabId="applinks" />
            {(tabData.applinks.loaded || hasActiveFilters('applinks')) && (
              <FilterBar section="applinks" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.applinks} hideBaseUrl={!isFullScan} />
            )}
            {tabData.applinks.loading ? <TabLoading /> : (
              <>
                {tabData.applinks.total > 0 ? getTabItems('applinks').map((link) => (
                  <ItemCard
                    key={link.id}
                    icon={Smartphone}
                    iconColor={applinksSubTab === 'crawl' ? 'text-cyber-blue' : 'text-cyber-green'}
                    badge={link.type}
                    badgeColor={applinksSubTab === 'crawl' ? 'bg-cyber-blue/20 text-cyber-blue' : (link.type === 'Play Store' ? 'bg-cyber-green/20 text-cyber-green' : 'bg-cyber-blue/20 text-cyber-blue')}
                    title={link.url}
                    subtitle={applinksSubTab === 'crawl' ? `Source: crawl` : `Found in ${link.file}`}
                    baseUrl={isFullScan ? (link.base || getBaseUrl(link.file)) : undefined}
                    borderColor={applinksSubTab === 'crawl' ? 'cyber-blue' : 'cyber-green'}
                    actions={
                      <>
                        <button onClick={() => copyToClipboard(link.url, link.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          {copiedId === link.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                        </button>
                        <a href={link.url} target="_blank" rel="noopener noreferrer" className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          <ExternalLink className="w-4 h-4 text-gray-400" />
                        </a>
                      </>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <Smartphone className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('applinks') ? 'No app store links match your filters' : `No app store links found in ${applinksSubTab === 'crawl' ? 'crawl results' : 'JS files'} during this scan`}
                    </p>
                  </div>
                )}
                <Pagination tabId="applinks" />
              </>
            )}
          </div>
        )}

        {activeTab === 'doclinks' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="Documentation Links" tabId="doclinks" hideExport={isFullScan} />
            <SourceSubTabs activeSubTab={doclinksSubTab} onSwitch={switchDoclinksSubTab} counts={docLinkCounts} jsColor="cyber-yellow" crawlColor="cyber-blue" tabId="doclinks" />
            {(tabData.doclinks.loaded || hasActiveFilters('doclinks')) && (
              <FilterBar section="doclinks" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.doclinks} hideBaseUrl={!isFullScan} />
            )}
            {tabData.doclinks.loading ? <TabLoading /> : (
              <>
                {tabData.doclinks.total > 0 ? getTabItems('doclinks').map((doc) => (
                  <ItemCard
                    key={doc.id}
                    icon={BookOpen}
                    iconColor={doclinksSubTab === 'crawl' ? 'text-cyber-blue' : 'text-cyber-yellow'}
                    badge={doc.type}
                    badgeColor={doclinksSubTab === 'crawl' ? 'bg-cyber-blue/20 text-cyber-blue' : 'bg-cyber-yellow/20 text-cyber-yellow'}
                    title={doc.url}
                    subtitle={doclinksSubTab === 'crawl' ? `Source: crawl` : `Found in ${doc.file}`}
                    baseUrl={isFullScan ? (doc.base || getBaseUrl(doc.file)) : undefined}
                    borderColor={doclinksSubTab === 'crawl' ? 'cyber-blue' : 'cyber-yellow'}
                    actions={
                      <>
                        <button onClick={() => copyToClipboard(doc.url, doc.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          {copiedId === doc.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                        </button>
                        <a href={doc.url} target="_blank" rel="noopener noreferrer" className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          <ExternalLink className="w-4 h-4 text-gray-400" />
                        </a>
                      </>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <BookOpen className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('doclinks') ? 'No documentation links match your filters' : `No documentation links found in ${doclinksSubTab === 'crawl' ? 'crawl results' : 'JS files'} during this scan`}
                    </p>
                  </div>
                )}
                <Pagination tabId="doclinks" />
              </>
            )}
          </div>
        )}

        {activeTab === 'sociallinks' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="Social Media Links" tabId="sociallinks" hideExport={isFullScan} />
            <SourceSubTabs activeSubTab={sociallinksSubTab} onSwitch={switchSociallinksSubTab} counts={socialLinkCounts} jsColor="cyber-red" crawlColor="cyber-blue" tabId="sociallinks" />
            {(tabData.sociallinks.loaded || hasActiveFilters('sociallinks')) && (
              <FilterBar section="sociallinks" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.sociallinks} hideBaseUrl={!isFullScan} />
            )}
            {tabData.sociallinks.loading ? <TabLoading /> : (
              <>
                {tabData.sociallinks.total > 0 ? getTabItems('sociallinks').map((social) => (
                  <ItemCard
                    key={social.id}
                    icon={Share2}
                    iconColor={sociallinksSubTab === 'crawl' ? 'text-cyber-blue' : 'text-cyber-red'}
                    badge={social.type}
                    badgeColor={sociallinksSubTab === 'crawl' ? 'bg-cyber-blue/20 text-cyber-blue' : 'bg-cyber-red/20 text-cyber-red'}
                    title={social.url}
                    subtitle={sociallinksSubTab === 'crawl' ? `Source: crawl` : `Found in ${social.file}`}
                    baseUrl={isFullScan ? (social.base || getBaseUrl(social.file)) : undefined}
                    borderColor={sociallinksSubTab === 'crawl' ? 'cyber-blue' : 'cyber-red'}
                    actions={
                      <>
                        <button onClick={() => copyToClipboard(social.url, social.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          {copiedId === social.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                        </button>
                        <a href={social.url} target="_blank" rel="noopener noreferrer" className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          <ExternalLink className="w-4 h-4 text-gray-400" />
                        </a>
                      </>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <Share2 className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('sociallinks') ? 'No social media links match your filters' : `No social media links found in ${sociallinksSubTab === 'crawl' ? 'crawl results' : 'JS files'} during this scan`}
                    </p>
                  </div>
                )}
                <Pagination tabId="sociallinks" />
              </>
            )}
          </div>
        )}

        {activeTab === 'urls' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="URLs" tabId="urls" hideExport={isFullScan} />
            <SourceSubTabs activeSubTab={urlsSubTab} onSwitch={switchUrlsSubTab} counts={urlCounts} jsColor="cyber-purple" crawlColor="cyber-blue" tabId="urls" />
            {(tabData.urls.loaded || hasActiveFilters('urls')) && (
              <FilterBar section="urls" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.urls} hideBaseUrl={!isFullScan} />
            )}
            {tabData.urls.loading ? <TabLoading /> : (
              <>
                {tabData.urls.total > 0 ? getTabItems('urls').map((item) => (
                  <ItemCard
                    key={item.id}
                    icon={Link2}
                    iconColor={urlsSubTab === 'crawl' ? 'text-cyber-blue' : 'text-cyber-purple'}
                    title={item.url}
                    subtitle={urlsSubTab === 'crawl' ? `Source: crawl` : `Found in ${item.file}`}
                    baseUrl={isFullScan ? (item.base || getBaseUrl(item.file)) : undefined}
                    borderColor={urlsSubTab === 'crawl' ? 'cyber-blue' : 'cyber-purple'}
                    actions={
                      <>
                        <button onClick={() => copyToClipboard(item.url, item.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          {copiedId === item.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                        </button>
                        <a href={item.url} target="_blank" rel="noopener noreferrer" className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                          <ExternalLink className="w-4 h-4 text-gray-400" />
                        </a>
                      </>
                    }
                  />
                )) : (
                  <div className="text-center py-8 sm:py-12">
                    <Link2 className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-400 text-sm sm:text-base">
                      {hasActiveFilters('urls')
                        ? 'No URLs match your filters'
                        : `No URLs found in ${urlsSubTab === 'crawl' ? 'crawl results' : 'JS files'} during this scan`}
                    </p>
                  </div>
                )}
                <Pagination tabId="urls" />
              </>
            )}
          </div>
        )}

        {activeTab === 'files' && (
          <div className="space-y-3 sm:space-y-4">
            <SectionHeader title="JS Files" tabId="files" hideExport />
            <FilesSubTabs
              activeSubTab={filesSubTab}
              onSwitch={(tab) => {
                setFilesSubTab(tab);
                if (tab === 'failed' && !failedDownloads.loaded) fetchFailedDownloads(1);
              }}
              counts={{ downloaded: tabData.files?.total || 0, failed: failedDownloads.total }}
              exporting={exporting}
              onExportFailed={exportFailedCSV}
            />

            {/* Downloaded sub-tab */}
            {filesSubTab === 'downloaded' && (
              <>
                {(tabData.files.loaded || hasActiveFilters('files')) && (
                  <FilterBar section="files" onFilterChange={updateFilter} onClearFilters={clearFilters} filters={filters.files} hideBaseUrl={!isFullScan} />
                )}
                {tabData.files.loading ? <TabLoading /> : (
                  <>
                    {tabData.files.total > 0 ? getTabItems('files').map((file) => (
                      <div key={file.id} className="cyber-card p-3 sm:p-4">
                        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 sm:gap-4">
                          <div className="flex items-start space-x-2 sm:space-x-3 min-w-0 flex-1">
                            <Download className="w-4 h-4 text-cyber-green flex-shrink-0 mt-0.5" />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-gray-400 text-xs">JS File:</span>
                              </div>
                              <span className="font-mono text-white text-xs sm:text-sm block break-all">{file.filename}</span>
                              {isFullScan && file.baseUrl && (
                                <div className="mt-1">
                                  <span className="text-gray-400 text-xs">Base URL: </span>
                                  <span className="text-gray-300 text-xs font-mono">{file.baseUrl}</span>
                                </div>
                              )}
                              <div className="flex items-center space-x-2 text-xs text-gray-400 mt-1">
                                <span>{file.size}</span>
                                <span>-</span>
                                <span>{file.type}</span>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center space-x-1 flex-shrink-0 self-end sm:self-start">
                            <button
                              onClick={() => viewFile(file)}
                              className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation"
                              title="View file content"
                            >
                              <Eye className="w-4 h-4 text-gray-400" />
                            </button>
                            <button onClick={() => copyToClipboard(file.url, file.id)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                              {copiedId === file.id ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                            </button>
                          </div>
                        </div>
                      </div>
                    )) : (
                      <div className="text-center py-8 sm:py-12">
                        <Download className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
                        <p className="text-gray-400 text-sm sm:text-base">
                          {hasActiveFilters('files') ? 'No files match your filters' : 'No files downloaded in this scan'}
                        </p>
                      </div>
                    )}
                    <Pagination tabId="files" />
                  </>
                )}
              </>
            )}

            {/* Failed sub-tab */}
            {filesSubTab === 'failed' && (
              <>
                {(failedDownloads.total > 0 || failedFilters.baseUrl || failedFilters.jsFile) && (
                  <FilterBar section="failed" onFilterChange={updateFailedFilter} onClearFilters={clearFailedFilters} filters={failedFilters} hideBaseUrl={!isFullScan} />
                )}

                {failedDownloads.loading ? <TabLoading /> : (
                  <>
                    {failedDownloads.total > 0 ? failedDownloads.data.map((item) => (
                      <div key={item.id} className="cyber-card p-3 sm:p-4 border-cyber-red/20">
                        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-2 sm:gap-4">
                          <div className="flex items-start space-x-2 sm:space-x-3 min-w-0 flex-1">
                            <AlertTriangle className="w-4 h-4 text-cyber-red flex-shrink-0 mt-0.5" />
                            <div className="min-w-0 flex-1">
                              <span className="font-mono text-white text-xs sm:text-sm block break-all">{item.js_url}</span>
                              {isFullScan && item.baseUrl && (
                                <div className="mt-1">
                                  <span className="text-gray-400 text-xs">Base URL: </span>
                                  <span className="text-gray-300 text-xs font-mono">{item.baseUrl}</span>
                                </div>
                              )}
                              <div className="mt-1">
                                <span className="px-1.5 py-0.5 rounded text-[10px] sm:text-xs bg-cyber-red/20 text-cyber-red">{item.error}</span>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center space-x-1 flex-shrink-0 self-end sm:self-start">
                            <button onClick={() => copyToClipboard(item.js_url, `failed-${item.id}`)} className="p-1.5 sm:p-2 hover:bg-cyber-light rounded touch-manipulation">
                              {copiedId === `failed-${item.id}` ? <CheckCircle className="w-4 h-4 text-cyber-green" /> : <Copy className="w-4 h-4 text-gray-400" />}
                            </button>
                          </div>
                        </div>
                      </div>
                    )) : (
                      <div className="text-center py-8 sm:py-12">
                        <CheckCircle className="w-10 h-10 sm:w-12 sm:h-12 text-cyber-green mx-auto mb-3 sm:mb-4" />
                        <p className="text-gray-400 text-sm sm:text-base">No failed downloads</p>
                      </div>
                    )}
                    {/* Failed downloads pagination */}
                    {failedDownloads.totalPages > 1 && (
                      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 mt-4 pt-4 border-t border-cyber-light">
                        <span className="text-gray-400 text-sm">
                          Showing {(failedDownloads.page - 1) * ITEMS_PER_PAGE + 1}-{Math.min(failedDownloads.page * ITEMS_PER_PAGE, failedDownloads.total)} of {failedDownloads.total} items
                        </span>
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => fetchFailedDownloads(1)}
                            disabled={failedDownloads.page === 1}
                            className="p-1.5 rounded hover:bg-cyber-light disabled:opacity-30 disabled:cursor-not-allowed transition-colors touch-manipulation"
                          >
                            <ChevronsLeft className="w-4 h-4 text-gray-400" />
                          </button>
                          <button
                            onClick={() => fetchFailedDownloads(failedDownloads.page - 1)}
                            disabled={failedDownloads.page === 1}
                            className="p-1.5 rounded hover:bg-cyber-light disabled:opacity-30 disabled:cursor-not-allowed transition-colors touch-manipulation"
                          >
                            <ChevronLeft className="w-4 h-4 text-gray-400" />
                          </button>
                          <span className="min-w-[32px] h-8 flex items-center justify-center rounded text-sm font-medium bg-cyber-blue text-cyber-dark">
                            {failedDownloads.page}
                          </span>
                          <button
                            onClick={() => fetchFailedDownloads(failedDownloads.page + 1)}
                            disabled={failedDownloads.page === failedDownloads.totalPages}
                            className="p-1.5 rounded hover:bg-cyber-light disabled:opacity-30 disabled:cursor-not-allowed transition-colors touch-manipulation"
                          >
                            <ChevronRight className="w-4 h-4 text-gray-400" />
                          </button>
                          <button
                            onClick={() => fetchFailedDownloads(failedDownloads.totalPages)}
                            disabled={failedDownloads.page === failedDownloads.totalPages}
                            className="p-1.5 rounded hover:bg-cyber-light disabled:opacity-30 disabled:cursor-not-allowed transition-colors touch-manipulation"
                          >
                            <ChevronsRight className="w-4 h-4 text-gray-400" />
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>
      </div>

      {/* File Viewer Modal */}
      {viewingFile && (
        <div className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center z-50 p-4" onClick={closeFileViewer}>
          <div className="bg-cyber-dark border border-cyber-light rounded-lg w-full max-w-6xl max-h-[90vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-cyber-light">
              <div className="flex-1 min-w-0">
                <h3 className="text-lg font-semibold text-white truncate">Viewing JS File</h3>
                <p className="text-sm text-gray-400 font-mono truncate">{viewingFile.filename}</p>
              </div>
              <button
                onClick={closeFileViewer}
                className="ml-4 p-2 hover:bg-cyber-light rounded transition-colors flex-shrink-0"
              >
                <X className="w-5 h-5 text-gray-400" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-auto p-4 bg-cyber-gray">
              {loadingFile ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-cyber-blue"></div>
                </div>
              ) : (
                <pre className="text-xs sm:text-sm text-gray-300 font-mono whitespace-pre-wrap break-words">
                  {fileContent}
                </pre>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-between p-4 border-t border-cyber-light">
              <div className="flex items-center space-x-4">
                {isFullScan && <span className="text-sm text-gray-400">Base URL: <span className="text-cyber-blue font-mono">{viewingFile.baseUrl}</span></span>}
                <span className="text-sm text-gray-400">Size: <span className="text-white">{viewingFile.size}</span></span>
              </div>
              <button
                onClick={() => copyToClipboard(fileContent, 'file-content')}
                className="cyber-button-secondary flex items-center space-x-2 text-sm py-2 px-4"
              >
                {copiedId === 'file-content' ? (
                  <>
                    <CheckCircle className="w-4 h-4" />
                    <span>Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span>Copy Content</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ScanDetails;
