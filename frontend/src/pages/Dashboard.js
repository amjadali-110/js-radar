import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  Search,
  Shield,
  AlertTriangle,
  CheckCircle,
  Clock,
  HardDrive,
  Globe,
  Link2,
  Cloud,
  FileCode,
  Server,
  Activity,
  TrendingUp,
  Plus
} from 'lucide-react';
import { apiService } from '../services/api';

const SCAN_TYPE_ICONS = {
  full: Activity,
  js_urls: Link2,
  file: FileCode,
};

const Dashboard = () => {
  const [stats, setStats] = useState({
    total_scans: 0,
    active_scans: 0,
    completed_scans: 0,
    failed_scans: 0,
    total_secrets: 0,
    total_endpoints: 0,
    total_subdomains: 0,
    total_cloud_resources: 0,
    total_storage_mb: 0,
    total_urls_scanned: 0
  });
  const [recentScans, setRecentScans] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const [statsData, scansData] = await Promise.all([
        apiService.getDashboardStats(),
        apiService.getScans()
      ]);

      setStats(statsData);
      setRecentScans(scansData.slice(0, 5));
    } catch (error) {
      console.error('Error fetching dashboard data:', error);
      setStats({
        total_scans: 0,
        active_scans: 0,
        completed_scans: 0,
        failed_scans: 0,
        total_secrets: 0,
        total_endpoints: 0,
        total_subdomains: 0,
        total_cloud_resources: 0,
        total_storage_mb: 0
      });
      setRecentScans([]);
    } finally {
      setLoading(false);
    }
  };

  const StatCard = ({ title, value, icon: Icon, color, trend }) => (
    <div className="cyber-card p-4 sm:p-5 lg:p-6">
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-gray-400 text-xs sm:text-sm font-medium truncate">{title}</p>
          <p className={`text-xl sm:text-2xl font-bold ${color}`}>{value}</p>
          {trend && (
            <div className="flex items-center mt-1">
              <TrendingUp className="w-3 h-3 sm:w-4 sm:h-4 text-cyber-green mr-1" />
              <span className="text-cyber-green text-xs sm:text-sm">{trend}</span>
            </div>
          )}
        </div>
        <div className={`p-2 sm:p-3 rounded-lg ${color.replace('text-', 'bg-').replace('cyber-', 'cyber-')} bg-opacity-20 flex-shrink-0 ml-3`}>
          <Icon className={`w-5 h-5 sm:w-6 sm:h-6 ${color}`} />
        </div>
      </div>
    </div>
  );

  const getStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return <Clock className="w-4 h-4 text-cyber-yellow" />;
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-cyber-green" />;
      case 'failed':
        return <AlertTriangle className="w-4 h-4 text-cyber-red" />;
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
      default:
        return 'status-pending';
    }
  };

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
          <h1 className="text-2xl sm:text-3xl font-bold text-white mb-1 sm:mb-1 tracking-tight">
            Dashboard
          </h1>
          <p className="text-gray-400 text-sm sm:text-base">Monitor your JavaScript security analysis</p>
        </div>
        <Link
          to="/scans/new"
          className="cyber-button-primary flex items-center justify-center space-x-2 w-full sm:w-auto shadow-[0_0_25px_rgba(0,212,255,0.45)]"
        >
          <Plus className="w-4 h-4" />
          <span>New Scan</span>
        </Link>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 sm:gap-4 lg:gap-6 mb-6 lg:mb-8">
        <StatCard
          title="Total Scans"
          value={stats.total_scans}
          icon={Search}
          color="text-cyber-blue"
        />
        <StatCard
          title="Active Scans"
          value={stats.active_scans}
          icon={Activity}
          color="text-cyber-yellow"
        />
        <StatCard
          title="Completed"
          value={stats.completed_scans}
          icon={CheckCircle}
          color="text-cyber-green"
        />
        <StatCard
          title="Failed"
          value={stats.failed_scans}
          icon={AlertTriangle}
          color="text-cyber-red"
        />
      </div>

      {/* Storage Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 sm:gap-4 lg:gap-6 mb-6 lg:mb-8">
        <StatCard
          title="Total Storage"
          value={stats.total_storage_mb >= 1024 ? `${(stats.total_storage_mb / 1024).toFixed(1)} GB` : `${(stats.total_storage_mb || 0).toFixed(1)} MB`}
          icon={HardDrive}
          color="text-cyber-yellow"
        />
      </div>

      {/* Recent Scans */}
      <div className="cyber-card p-4 sm:p-5 lg:p-6">
        <div className="flex items-center justify-between gap-3 mb-4 sm:mb-6">
          <h2 className="text-lg sm:text-xl font-semibold text-white">Recent Scans</h2>
          <Link
            to="/scans"
            className="text-cyber-blue hover:text-cyber-blue/80 text-sm font-medium"
          >
            View All
          </Link>
        </div>

        {recentScans.length > 0 ? (
          <>
            {/* Desktop Table */}
            <div className="hidden md:block overflow-x-auto -mx-4 sm:-mx-5 lg:-mx-6 px-4 sm:px-5 lg:px-6">
              <table className="cyber-table min-w-full">
                <thead>
                  <tr>
                    <th className="px-3 sm:px-4 lg:px-6 py-2 sm:py-3">Scan Name</th>
                    <th className="px-3 sm:px-4 lg:px-6 py-2 sm:py-3">Target URL</th>
                    <th className="px-3 sm:px-4 lg:px-6 py-2 sm:py-3">Status</th>
                    <th className="px-3 sm:px-4 lg:px-6 py-2 sm:py-3">Created</th>
                    <th className="px-3 sm:px-4 lg:px-6 py-2 sm:py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {recentScans.map((scan) => (
                    <tr key={scan.id} className="hover:bg-cyber-light/50 transition-colors">
                      {(() => {
                        const ScanTypeIcon = getScanTypeIcon(scan.scan_type);
                        return (
                      <td className="px-3 sm:px-4 lg:px-6 py-3 sm:py-4">
                        <div className="flex items-center space-x-2 sm:space-x-3">
                          <ScanTypeIcon className="w-4 h-4 text-cyber-blue flex-shrink-0" />
                          <span className="font-medium text-white truncate max-w-[150px] lg:max-w-none">{scan.name}</span>
                        </div>
                      </td>
                        );
                      })()}
                      <td className="px-3 sm:px-4 lg:px-6 py-3 sm:py-4">
                        <span className="text-gray-300 font-mono text-xs sm:text-sm truncate block max-w-[200px]">{scan.target_url}</span>
                      </td>
                      <td className="px-3 sm:px-4 lg:px-6 py-3 sm:py-4">
                        <div className="flex items-center space-x-2">
                          {getStatusIcon(scan.status)}
                          <span className={getStatusClass(scan.status)}>
                            {scan.status.charAt(0).toUpperCase() + scan.status.slice(1)}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 sm:px-4 lg:px-6 py-3 sm:py-4">
                        <span className="text-gray-400 text-sm">
                          {new Date(scan.created_at).toLocaleDateString()}
                        </span>
                      </td>
                      <td className="px-3 sm:px-4 lg:px-6 py-3 sm:py-4">
                        <Link
                          to={`/scans/${scan.id}`}
                          className="text-cyber-blue hover:text-cyber-blue/80 text-sm font-medium"
                        >
                          View
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile Card View */}
            <div className="md:hidden space-y-2.5">
              {recentScans.map((scan) => (
                <Link
                  key={scan.id}
                  to={`/scans/${scan.id}`}
                  className="block bg-cyber-light/50 rounded-lg p-4 hover:bg-cyber-light transition-colors"
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    {(() => {
                      const ScanTypeIcon = getScanTypeIcon(scan.scan_type);
                      return (
                    <div className="flex items-center space-x-2 min-w-0 flex-1">
                      <ScanTypeIcon className="w-4 h-4 text-cyber-blue flex-shrink-0" />
                      <span className="font-medium text-white truncate">{scan.name}</span>
                    </div>
                      );
                    })()}
                    <div className="flex items-center space-x-1.5 flex-shrink-0 ml-1">
                      {getStatusIcon(scan.status)}
                      <span className={`${getStatusClass(scan.status)} text-xs`}>
                        {scan.status.charAt(0).toUpperCase() + scan.status.slice(1)}
                      </span>
                    </div>
                  </div>
                  <p className="text-gray-400 font-mono text-xs truncate mb-2">{scan.target_url}</p>
                  <p className="text-gray-500 text-xs">
                    {new Date(scan.created_at).toLocaleDateString()}
                  </p>
                </Link>
              ))}
            </div>
          </>
        ) : (
          <div className="text-center py-8 sm:py-12">
            <Shield className="w-10 h-10 sm:w-12 sm:h-12 text-gray-600 mx-auto mb-3 sm:mb-4" />
            <h3 className="text-base sm:text-lg font-medium text-gray-400 mb-2">No scans yet</h3>
            <p className="text-gray-500 text-sm mb-4">Create your first scan to start analyzing</p>
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
    </div>
  );
};

export default Dashboard;
