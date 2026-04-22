import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  Plus,
  Play,
  Pause,
  Trash2,
  Eye,
  Calendar,
  Shield,
  CheckCircle,
  Clock,
  AlertTriangle,
  XCircle,
  ChevronDown,
  HardDrive,
  Cpu,
  Activity,
  Link2,
  FileCode
} from 'lucide-react';
import { apiService } from '../services/api';

const ACTIVE_SCAN_STATUSES = new Set(['running', 'pending']);
const SCAN_TYPE_LABELS = {
  full: 'Full Scan',
  js_urls: 'JS URLs Scan',
  file: 'File Scan',
};
const SCAN_TYPE_ICONS = {
  full: Activity,
  js_urls: Link2,
  file: FileCode,
};

const Scans = () => {
  const [scans, setScans] = useState([]);
  const [filteredScans, setFilteredScans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [scanTypeFilter, setScanTypeFilter] = useState('all');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortOrder, setSortOrder] = useState('desc');
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    fetchScans({ showLoader: true });
  }, []);

  useEffect(() => {
    const hasActiveScans = scans.some(scan => ACTIVE_SCAN_STATUSES.has(scan.status));
    let intervalId;
    if (hasActiveScans) {
      intervalId = setInterval(() => {
        fetchScans({ showLoader: false });
      }, 5000);
    }
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [scans]);

  useEffect(() => {
    filterAndSortScans();
  }, [scans, searchTerm, statusFilter, scanTypeFilter, sortBy, sortOrder]);

  const fetchScans = async ({ showLoader = false } = {}) => {
    try {
      if (showLoader) {
        setLoading(true);
      }

      const data = await apiService.getScans();

      const enrichedScans = await Promise.all(
        data.map(async (scan) => {
          if (!ACTIVE_SCAN_STATUSES.has(scan.status)) {
            return scan;
          }

          try {
            const counts = await apiService.getScanCounts(scan.id);
            return {
              ...scan,
              secrets_count: counts?.secrets ?? scan.secrets_count,
              endpoints_count: counts?.endpoints ?? scan.endpoints_count,
              subdomains_count: counts?.subdomains ?? scan.subdomains_count,
              files_count: counts?.files ?? scan.files_count,
            };
          } catch (error) {
            console.warn(`Live counts unavailable for scan ${scan.id}:`, error);
            return scan;
          }
        })
      );

      setScans(enrichedScans);
    } catch (error) {
      console.error('Error fetching scans:', error);
      setScans([]);
    } finally {
      if (showLoader) {
        setLoading(false);
      }
    }
  };

  const filterAndSortScans = () => {
    let filtered = scans.filter(scan => {
      const matchesSearch = scan.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                           scan.target_url.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesStatus = statusFilter === 'all' || scan.status === statusFilter;
      const normalizedType = scan.scan_type || 'full';
      const matchesScanType = scanTypeFilter === 'all' || normalizedType === scanTypeFilter;
      return matchesSearch && matchesStatus && matchesScanType;
    });

    filtered.sort((a, b) => {
      let aValue = a[sortBy];
      let bValue = b[sortBy];

      if (sortBy === 'created_at') {
        aValue = new Date(aValue);
        bValue = new Date(bValue);
      }

      if (sortOrder === 'asc') {
        return aValue > bValue ? 1 : -1;
      } else {
        return aValue < bValue ? 1 : -1;
      }
    });

    setFilteredScans(filtered);
  };

  const handleStartScan = async (scanId) => {
    try {
      await apiService.startScan(scanId);
      fetchScans({ showLoader: false });
    } catch (error) {
      console.error('Error starting scan:', error);
    }
  };

  const handleStopScan = async (scanId) => {
    try {
      await apiService.stopScan(scanId);
      fetchScans({ showLoader: false });
    } catch (error) {
      console.error('Error stopping scan:', error);
    }
  };

  const handleDeleteScan = async (scanId) => {
    if (window.confirm('Are you sure you want to delete this scan?')) {
      try {
        await apiService.deleteScan(scanId);
        fetchScans({ showLoader: false });
      } catch (error) {
        console.error('Error deleting scan:', error);
      }
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return <Clock className="w-4 h-4 text-cyber-yellow" />;
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-cyber-green" />;
      case 'failed':
        return <AlertTriangle className="w-4 h-4 text-cyber-red" />;
      case 'pending':
        return <XCircle className="w-4 h-4 text-gray-400" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusClass = (status) => {
    switch (status) {
      case 'running':
        return 'status-running';
      case 'completed':
        return 'status-completed';
      case 'failed':
        return 'status-failed';
      case 'pending':
        return 'status-pending';
      default:
        return 'status-pending';
    }
  };

  const getScanTypeLabel = (scanType) => SCAN_TYPE_LABELS[scanType] || 'Full';
  const getScanTypeIcon = (scanType) => SCAN_TYPE_ICONS[scanType] || Activity;

  if (loading) {
    return (
      <div className="flex-1 p-4 sm:p-6 lg:p-8">
        <div className="flex items-center justify-center h-full">
          <div className="animate-spin rounded-full h-10 w-10 sm:h-12 sm:w-12 border-b-2 border-cyber-blue"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 p-3 sm:p-6 lg:p-8 overflow-auto scrollbar-thin">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6 lg:mb-8 pt-12 lg:pt-0">
        <div className="space-y-1">
          <h1 className="text-2xl sm:text-3xl font-bold text-white mb-1 sm:mb-1 tracking-tight">Scans</h1>
          <p className="text-gray-400 text-sm sm:text-base">Manage and monitor your security scans</p>
        </div>
        <Link
          to="/scans/new"
          className="cyber-button-primary flex items-center justify-center space-x-2 w-full sm:w-auto shadow-[0_0_25px_rgba(0,212,255,0.45)]"
        >
          <Plus className="w-4 h-4" />
          <span>New Scan</span>
        </Link>
      </div>

      {/* Filters and Search */}
      <div className="cyber-card p-3 sm:p-5 lg:p-6 mb-4 sm:mb-6">
        {/* Mobile Filter Toggle */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="flex items-center justify-between w-full md:hidden mb-4"
        >
          <span className="text-white font-medium">Filters & Search</span>
          <ChevronDown className={`w-5 h-5 text-gray-400 transition-transform ${showFilters ? 'rotate-180' : ''}`} />
        </button>

        {/* Filters Content */}
        <div className={`${showFilters ? 'block' : 'hidden'} md:block`}>
          <div className="flex flex-col gap-3 sm:gap-4">
            {/* Search Input */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
              <input
                type="text"
                placeholder="Search scans..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="cyber-input pl-10 w-full"
              />
            </div>

            {/* Filter Row */}
            <div className="flex flex-col sm:flex-row gap-2.5 sm:gap-4 mobile-horizontal-scroll sm:overflow-visible">
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="cyber-input flex-1 sm:flex-none sm:w-40"
              >
                <option value="all">All Status</option>
                <option value="pending">Pending</option>
                <option value="running">Running</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
              </select>

              <select
                value={scanTypeFilter}
                onChange={(e) => setScanTypeFilter(e.target.value)}
                className="cyber-input flex-1 sm:flex-none sm:w-48"
              >
                <option value="all">All Scan Types</option>
                <option value="full">Full Scan</option>
                <option value="js_urls">JS URLs Scan</option>
                <option value="file">File Scan</option>
              </select>

              <select
                value={`${sortBy}-${sortOrder}`}
                onChange={(e) => {
                  const [field, order] = e.target.value.split('-');
                  setSortBy(field);
                  setSortOrder(order);
                }}
                className="cyber-input flex-1 sm:flex-none sm:w-40"
              >
                <option value="created_at-desc">Newest First</option>
                <option value="created_at-asc">Oldest First</option>
                <option value="name-asc">Name A-Z</option>
                <option value="name-desc">Name Z-A</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Scans Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 sm:gap-5 lg:gap-6">
        {filteredScans.map((scan) => (
          <div key={scan.id} className="cyber-card p-3 sm:p-5 lg:p-6 hover:border-cyber-blue/50 transition-all duration-300">
            {/* Header */}
            {(() => {
              const ScanTypeIcon = getScanTypeIcon(scan.scan_type);
              return (
            <div className="flex items-start justify-between mb-3 sm:mb-4">
              <div className="flex items-center space-x-2 sm:space-x-3 min-w-0 flex-1">
                <div className="p-1.5 sm:p-2 bg-cyber-blue/20 rounded-lg flex-shrink-0">
                  <ScanTypeIcon className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-blue" />
                </div>
                <div className="min-w-0 flex-1">
                  <h3 className="font-semibold text-white text-sm sm:text-base truncate">{scan.name}</h3>
                  <p className="mt-0.2 text-[10px] sm:text-xs text-cyber-blue truncate">
                    {getScanTypeLabel(scan.scan_type)}
                  </p>
                </div>
              </div>
            </div>
              );
            })()}

            {/* Status and Date */}
            <div className="flex items-center justify-between gap-2 mb-3 sm:mb-4">
              <div className="flex items-center space-x-2">
                {getStatusIcon(scan.status)}
                <span className={`${getStatusClass(scan.status)} text-xs sm:text-sm`}>
                  {scan.status.charAt(0).toUpperCase() + scan.status.slice(1)}
                </span>
              </div>
              <div className="flex items-center space-x-1 text-gray-400 text-[11px] sm:text-sm flex-shrink-0">
                <Calendar className="w-3 h-3 sm:w-4 sm:h-4" />
                <span>{new Date(scan.created_at).toLocaleDateString()}</span>
              </div>
            </div>

            {/* Results Summary */}
            <div className="grid grid-cols-4 gap-2 sm:gap-4 mb-3 sm:mb-4">
              <div className="text-center">
                <p className="text-cyber-red font-bold text-base sm:text-lg">{scan.secrets_count}</p>
                <p className="text-gray-400 text-[10px] sm:text-xs">Secrets</p>
              </div>
              <div className="text-center">
                <p className="text-cyber-blue font-bold text-base sm:text-lg">{scan.endpoints_count}</p>
                <p className="text-gray-400 text-[10px] sm:text-xs">Endpoints</p>
              </div>
              <div className="text-center">
                <p className="text-cyber-green font-bold text-base sm:text-lg">{scan.subdomains_count}</p>
                <p className="text-gray-400 text-[10px] sm:text-xs">Subdomains</p>
              </div>
              <div className="text-center">
                <p className="text-cyber-purple font-bold text-base sm:text-lg">{scan.files_count}</p>
                <p className="text-gray-400 text-[10px] sm:text-xs">JS Files</p>
              </div>
            </div>

            {/* Resource Usage */}
            {scan.status !== 'pending' && (
              <div className="flex items-center justify-between mb-3 sm:mb-4 px-2 py-1.5 bg-cyber-dark/50 rounded-lg">
                <div className="flex items-center space-x-1.5 text-gray-400 text-[10px] sm:text-xs">
                  <HardDrive className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-cyber-yellow" />
                  <span>{scan.storage_mb >= 1024 ? `${(scan.storage_mb / 1024).toFixed(1)} GB` : `${(scan.storage_mb || 0).toFixed(1)} MB`}</span>
                </div>
                <div className="flex items-center space-x-1.5 text-gray-400 text-[10px] sm:text-xs">
                  <Cpu className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-cyber-purple" />
                  {scan.status === 'running' && scan.current_ram_mb != null ? (
                    <span>RAM: {scan.current_ram_mb >= 1024 ? `${(scan.current_ram_mb / 1024).toFixed(1)} GB` : `${scan.current_ram_mb.toFixed(1)} MB`}</span>
                  ) : (
                    <span>Peak: {scan.peak_ram_mb >= 1024 ? `${(scan.peak_ram_mb / 1024).toFixed(1)} GB` : `${(scan.peak_ram_mb || 0).toFixed(1)} MB`}</span>
                  )}
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex items-center justify-between flex-nowrap gap-3 pt-3 sm:pt-4 border-t border-cyber-light">
              <div className="flex items-center space-x-1 sm:space-x-2 flex-shrink-0">
                {scan.status === 'pending' && (
                  <button
                    onClick={() => handleStartScan(scan.id)}
                    className="p-2 sm:p-2.5 hover:bg-cyber-green/20 rounded-lg transition-colors touch-manipulation"
                    title="Start Scan"
                  >
                    <Play className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-green" />
                  </button>
                )}
                {scan.status === 'running' && (
                  <button
                    onClick={() => handleStopScan(scan.id)}
                    className="p-2 sm:p-2.5 hover:bg-cyber-yellow/20 rounded-lg transition-colors touch-manipulation"
                    title="Stop Scan"
                  >
                    <Pause className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-yellow" />
                  </button>
                )}
                <button
                  onClick={() => handleDeleteScan(scan.id)}
                  className="p-2 sm:p-2.5 hover:bg-cyber-red/20 rounded-lg transition-colors touch-manipulation"
                  title="Delete Scan"
                >
                  <Trash2 className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-red" />
                </button>
              </div>
              <Link
                to={`/scans/${scan.id}`}
                className="cyber-button-secondary inline-flex items-center justify-center space-x-1.5 sm:space-x-2 text-xs sm:text-sm py-1.5 sm:py-2 px-2.5 sm:px-4 w-auto min-w-[96px] flex-shrink-0 ml-auto"
              >
                <Eye className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
                <span className="hidden xs:inline">View</span>
                <span className="xs:hidden">Details</span>
              </Link>
            </div>
          </div>
        ))}
      </div>

      {filteredScans.length === 0 && (
        <div className="text-center py-8 sm:py-12">
          <Shield className="w-12 h-12 sm:w-16 sm:h-16 text-gray-400 mx-auto mb-3 sm:mb-4" />
          <h3 className="text-lg sm:text-xl font-semibold text-gray-400 mb-2">No scans found</h3>
          <p className="text-gray-500 text-sm sm:text-base mb-4 sm:mb-6 px-4">
            {searchTerm || statusFilter !== 'all'
              ? 'Try adjusting your search or filter criteria'
              : 'Get started by creating your first security scan'
            }
          </p>
          <Link
            to="/scans/new"
            className="cyber-button-primary inline-flex items-center space-x-2"
          >
            <Plus className="w-4 h-4" />
            <span>Create New Scan</span>
          </Link>
        </div>
      )}
    </div>
  );
};

export default Scans;
