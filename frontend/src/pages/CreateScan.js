import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Globe,
  Settings,
  AlertCircle,
  Upload,
  FileText,
  X,
  Plus,
  ChevronDown,
  ChevronRight,
  Shield,
  Activity,
  Link as LinkIcon,
  FileCode,
} from 'lucide-react';
import { apiService } from '../services/api';

const SCAN_TYPES = [
  {
    id: 'full',
    title: 'Full Scan',
    description: 'Includes crawling and complete JavaScript analysis',
    icon: Activity,
  },
  {
    id: 'js_urls',
    title: 'Analyze JS URLs',
    description: 'Analyze one or more JavaScript URLs directly',
    icon: LinkIcon,
  },
  {
    id: 'file',
    title: 'Analyze a File',
    description: 'Upload a local JavaScript file and analyze it',
    icon: FileCode,
  },
];

const CreateScan = () => {
  const navigate = useNavigate();
  const [selectedScanType, setSelectedScanType] = useState('');
  const [formData, setFormData] = useState({
    name: '',
    urls: '',
    parallel: 3,
    concurrency: 2,
    depth: 1,
    delay: 0,
    cookie: '',
    headers: ['']
  });

  // When scan type changes, set appropriate parallel default
  const prevScanTypeRef = React.useRef(selectedScanType);
  React.useEffect(() => {
    if (prevScanTypeRef.current !== selectedScanType) {
      prevScanTypeRef.current = selectedScanType;
      if (selectedScanType === 'js_urls') {
        setFormData(prev => ({ ...prev, parallel: 5 }));
      } else if (selectedScanType === 'full') {
        setFormData(prev => ({ ...prev, parallel: 3 }));
      }
    }
  }, [selectedScanType]);
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState({});
  const [uploadedFile, setUploadedFile] = useState(null);
  const [inputMethod, setInputMethod] = useState('textarea'); // used for full/js_urls URL list input
  const [showAdvanced, setShowAdvanced] = useState(false);

  const isFullScan = selectedScanType === 'full';
  const isJsUrlsScan = selectedScanType === 'js_urls';
  const isFileScan = selectedScanType === 'file';
  const requiresUrls = isFullScan || isJsUrlsScan;

  const handleInputChange = (e) => {
    const { name, value, type } = e.target;
    let parsedValue = value;
    if (type === 'number') {
      const num = parseInt(value);
      parsedValue = isNaN(num) ? '' : num;
    }
    setFormData(prev => ({
      ...prev,
      [name]: parsedValue
    }));

    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: '' }));
    }
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (isFileScan) {
        if (!file.name.toLowerCase().endsWith('.js')) {
          setErrors(prev => ({ ...prev, file: 'Please upload a .js file' }));
          return;
        }
        setUploadedFile(file);
        setErrors(prev => ({ ...prev, file: '' }));
      } else {
        if (!file.name.endsWith('.txt')) {
          setErrors(prev => ({ ...prev, file: 'Please upload a .txt file' }));
          return;
        }

        const reader = new FileReader();
        reader.onload = (event) => {
          const content = event.target.result;
          setFormData(prev => ({ ...prev, urls: content }));
          setUploadedFile(file);
          setErrors(prev => ({ ...prev, file: '', urls: '' }));
        };
        reader.readAsText(file);
      }
    }
  };

  const removeFile = () => {
    setUploadedFile(null);
    setFormData(prev => ({ ...prev, urls: '' }));
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Scan name is required';
    }

    if (requiresUrls && !formData.urls.trim()) {
      newErrors.urls = 'At least one URL is required';
    } else if (requiresUrls) {
      const urls = formData.urls.split('\n').filter(url => url.trim());
      if (urls.length === 0) {
        newErrors.urls = 'At least one valid URL is required';
      } else {
        const invalidUrls = urls.filter(url => {
          const trimmed = url.trim();
          if (!trimmed || trimmed.startsWith('#')) return false;
          try {
            new URL(trimmed);
            return false;
          } catch {
            return true;
          }
        });
        if (invalidUrls.length > 0) {
          newErrors.urls = `Invalid URL(s): ${invalidUrls.slice(0, 3).join(', ')}${invalidUrls.length > 3 ? '...' : ''}`;
        }
      }
    }

    if ((isFullScan || isJsUrlsScan) && (formData.parallel < 1 || formData.parallel > 10)) {
      newErrors.parallel = 'Parallel must be between 1 and 10';
    }

    if (isFullScan && (formData.concurrency < 1 || formData.concurrency > 10)) {
      newErrors.concurrency = 'Concurrency must be between 1 and 10';
    }
    if (isFileScan && !uploadedFile) {
      newErrors.file = 'Please upload a JavaScript file';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setLoading(true);
    try {
      const filteredHeaders = formData.headers.filter(h => h.trim());
      let scan;

      if (isFileScan) {
        const payload = new FormData();
        payload.append('name', formData.name.trim());
        payload.append('scan_type', 'file');
        payload.append('js_file', uploadedFile);
        scan = await apiService.createScan(payload, true);
      } else {
        const scanData = {
          name: formData.name.trim(),
          scan_type: selectedScanType,
          target_url: formData.urls.trim(),
          parallel: formData.parallel,
          concurrency: formData.concurrency,
          depth: formData.depth,
          delay: formData.delay,
          cookie: formData.cookie.trim(),
          headers: filteredHeaders.length > 0 ? JSON.stringify(filteredHeaders) : ''
        };
        scan = await apiService.createScan(scanData);
      }

      navigate(`/scans/${scan.id}`);
    } catch (error) {
      console.error('Error creating scan:', error);
      const serverMsg = error.response?.data?.error;
      const submitError = serverMsg
        ? `Failed to create scan: ${serverMsg}`
        : error.message?.includes('Network Error')
          ? 'Cannot reach the backend server. Make sure the backend is running on port 3001.'
          : 'Failed to create scan. Please try again.';
      setErrors({ submit: submitError });
    } finally {
      setLoading(false);
    }
  };

  const getUrlCount = () => {
    if (!formData.urls.trim()) return 0;
    return formData.urls.split('\n').filter(url => {
      const trimmed = url.trim();
      return trimmed && !trimmed.startsWith('#');
    }).length;
  };

  const scanTypeTitle = useMemo(() => {
    const selected = SCAN_TYPES.find(type => type.id === selectedScanType);
    return selected ? selected.title : 'Create New Scan';
  }, [selectedScanType]);

  return (
    <div className="flex-1 p-3 sm:p-6 lg:p-8 overflow-auto scrollbar-thin">
      {/* Header */}
      <div className="flex items-start sm:items-center space-x-3 sm:space-x-4 mb-6 lg:mb-8 pt-12 lg:pt-0">
        <button
          onClick={() => navigate('/scans')}
          className="p-2 hover:bg-cyber-light rounded-lg transition-colors flex-shrink-0 touch-manipulation"
        >
          <ArrowLeft className="w-5 h-5 text-gray-400" />
        </button>
        <div className="space-y-1">
          <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold text-white mb-1 sm:mb-1 tracking-tight">
            {scanTypeTitle}
          </h1>
          <p className="text-gray-400 text-sm sm:text-base">
            {selectedScanType ? 'Configure your JavaScript security analysis' : 'Choose a scan type to begin'}
          </p>
        </div>
      </div>

      {!selectedScanType && (
        <div className="max-w-5xl grid grid-cols-1 md:grid-cols-3 gap-3 sm:gap-5">
          {SCAN_TYPES.map((type) => {
            const Icon = type.icon;
            return (
              <button
                key={type.id}
                type="button"
                onClick={() => setSelectedScanType(type.id)}
                className="cyber-card p-4 sm:p-6 text-left border border-cyber-light hover:border-cyber-blue/70 transition-colors"
              >
                <div className="mb-4 inline-flex p-2.5 rounded-lg bg-cyber-blue/20">
                  <Icon className="w-5 h-5 text-cyber-blue" />
                </div>
                <h2 className="text-white font-semibold text-lg mb-1">{type.title}</h2>
                <p className="text-gray-400 text-sm">{type.description}</p>
              </button>
            );
          })}
        </div>
      )}

      {selectedScanType && (
      <form onSubmit={handleSubmit} className="max-w-4xl">
        {/* Basic Information */}
        <div className="cyber-card p-3 sm:p-5 lg:p-6 mb-4 sm:mb-6">
          <div className="flex items-center space-x-3 mb-4 sm:mb-6">
            <div className="p-1.5 sm:p-2 bg-cyber-blue/20 rounded-lg flex-shrink-0">
              <Globe className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-blue" />
            </div>
              <h2 className="text-lg sm:text-xl font-semibold text-white">Basic Information</h2>
          </div>

          <div className="mb-4 sm:mb-6">
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Scan Name *
            </label>
            <input
              type="text"
              name="name"
              value={formData.name}
              onChange={handleInputChange}
              placeholder="e.g., my_security_scan"
              className={`cyber-input w-full ${errors.name ? 'border-cyber-red' : ''}`}
            />
            {errors.name && (
              <p className="text-cyber-red text-sm mt-1 flex items-center">
                <AlertCircle className="w-4 h-4 mr-1 flex-shrink-0" />
                <span>{errors.name}</span>
              </p>
            )}
            <p className="text-gray-500 text-xs mt-1">This will be used as the scan folder name</p>
          </div>
        </div>

        {/* Target URLs */}
        {requiresUrls && (
        <div className="cyber-card p-3 sm:p-5 lg:p-6 mb-4 sm:mb-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-0 mb-4 sm:mb-6">
            <div className="flex items-center space-x-3">
              <div className="p-1.5 sm:p-2 bg-cyber-green/20 rounded-lg flex-shrink-0">
                <FileText className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-green" />
              </div>
              <h2 className="text-lg sm:text-xl font-semibold text-white">
                {isFullScan ? 'Target URLs' : 'JavaScript URLs'}
              </h2>
            </div>
            <div className="flex items-center space-x-2 overflow-x-auto mobile-horizontal-scroll">
              <button
                type="button"
                onClick={() => setInputMethod('textarea')}
                className={`px-3 py-1.5 rounded text-xs sm:text-sm transition-colors touch-manipulation ${
                  inputMethod === 'textarea'
                    ? 'bg-cyber-blue text-cyber-dark'
                    : 'bg-cyber-light text-gray-300 hover:bg-cyber-light/80'
                }`}
              >
                Enter URLs
              </button>
              <button
                type="button"
                onClick={() => setInputMethod('file')}
                className={`px-3 py-1.5 rounded text-xs sm:text-sm transition-colors touch-manipulation ${
                  inputMethod === 'file'
                    ? 'bg-cyber-blue text-cyber-dark'
                    : 'bg-cyber-light text-gray-300 hover:bg-cyber-light/80'
                }`}
              >
                Upload File
              </button>
            </div>
          </div>

          {inputMethod === 'textarea' ? (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                {isFullScan ? 'URLs to Scan' : 'JavaScript URLs'} * <span className="text-gray-500 text-xs sm:text-sm">(one per line)</span>
              </label>
              <textarea
                name="urls"
                value={formData.urls}
                onChange={handleInputChange}
                placeholder={isFullScan
                  ? 'https://example.com&#10;https://api.example.com&#10;# Comments start with #'
                  : 'https://cdn.example.com/app.js&#10;https://static.example.com/main.bundle.js&#10;# Comments start with #'}
                rows={8}
                className={`cyber-input w-full resize-none font-mono text-xs sm:text-sm ${errors.urls ? 'border-cyber-red' : ''}`}
              />
              {errors.urls && (
                <p className="text-cyber-red text-sm mt-1 flex items-start">
                  <AlertCircle className="w-4 h-4 mr-1 flex-shrink-0 mt-0.5" />
                  <span>{errors.urls}</span>
                </p>
              )}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mt-2 gap-1">
                <p className="text-gray-500 text-xs">Enter one URL per line. Use # for comments.</p>
                <span className="text-cyber-blue text-sm font-medium">{getUrlCount()} URL(s)</span>
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Upload URL File * <span className="text-gray-500 text-xs sm:text-sm">(.txt)</span>
              </label>

              {!uploadedFile ? (
                <div
                  className={`border-2 border-dashed rounded-lg p-6 sm:p-8 text-center transition-colors ${
                    errors.file || errors.urls ? 'border-cyber-red' : 'border-cyber-light hover:border-cyber-blue'
                  }`}
                >
                  <input
                    type="file"
                    accept=".txt"
                    onChange={handleFileUpload}
                    className="hidden"
                    id="file-upload"
                  />
                  <label htmlFor="file-upload" className="cursor-pointer touch-manipulation">
                    <Upload className="w-10 h-10 sm:w-12 sm:h-12 text-gray-500 mx-auto mb-3 sm:mb-4" />
                    <p className="text-gray-300 text-sm sm:text-base mb-1 sm:mb-2">Click to upload or drag and drop</p>
                    <p className="text-gray-500 text-xs sm:text-sm">TXT file containing URLs</p>
                  </label>
                </div>
              ) : (
                <div className="bg-cyber-light rounded-lg p-3 sm:p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2 sm:space-x-3 min-w-0 flex-1">
                      <FileText className="w-6 h-6 sm:w-8 sm:h-8 text-cyber-green flex-shrink-0" />
                      <div className="min-w-0 flex-1">
                        <p className="text-white font-medium text-sm sm:text-base truncate">{uploadedFile.name}</p>
                        <p className="text-gray-400 text-xs sm:text-sm">{getUrlCount()} URL(s) found</p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={removeFile}
                      className="p-2 hover:bg-cyber-red/20 rounded-lg transition-colors touch-manipulation flex-shrink-0"
                    >
                      <X className="w-5 h-5 text-cyber-red" />
                    </button>
                  </div>
                </div>
              )}

              {(errors.file || errors.urls) && (
                <p className="text-cyber-red text-sm mt-2 flex items-start">
                  <AlertCircle className="w-4 h-4 mr-1 flex-shrink-0 mt-0.5" />
                  <span>{errors.file || errors.urls}</span>
                </p>
              )}
            </div>
          )}
        </div>
        )}

        {isFileScan && (
          <div className="cyber-card p-3 sm:p-5 lg:p-6 mb-4 sm:mb-6">
            <div className="flex items-center space-x-3 mb-4 sm:mb-6">
              <div className="p-1.5 sm:p-2 bg-cyber-green/20 rounded-lg flex-shrink-0">
                <FileCode className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-green" />
              </div>
              <h2 className="text-lg sm:text-xl font-semibold text-white">Upload JavaScript File</h2>
            </div>

            {!uploadedFile ? (
              <div className={`border-2 border-dashed rounded-lg p-6 sm:p-8 text-center transition-colors ${errors.file ? 'border-cyber-red' : 'border-cyber-light hover:border-cyber-blue'}`}>
                <input type="file" accept=".js" onChange={handleFileUpload} className="hidden" id="js-file-upload" />
                <label htmlFor="js-file-upload" className="cursor-pointer touch-manipulation">
                  <Upload className="w-10 h-10 sm:w-12 sm:h-12 text-gray-500 mx-auto mb-3 sm:mb-4" />
                  <p className="text-gray-300 text-sm sm:text-base mb-1 sm:mb-2">Click to upload a JavaScript file</p>
                  <p className="text-gray-500 text-xs sm:text-sm">Only .js files are accepted</p>
                </label>
              </div>
            ) : (
              <div className="bg-cyber-light rounded-lg p-3 sm:p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2 sm:space-x-3 min-w-0 flex-1">
                    <FileCode className="w-6 h-6 sm:w-8 sm:h-8 text-cyber-green flex-shrink-0" />
                    <div className="min-w-0 flex-1">
                      <p className="text-white font-medium text-sm sm:text-base truncate">{uploadedFile.name}</p>
                      <p className="text-gray-400 text-xs sm:text-sm">{Math.round(uploadedFile.size / 1024)} KB</p>
                    </div>
                  </div>
                  <button type="button" onClick={removeFile} className="p-2 hover:bg-cyber-red/20 rounded-lg transition-colors touch-manipulation flex-shrink-0">
                    <X className="w-5 h-5 text-cyber-red" />
                  </button>
                </div>
              </div>
            )}

            {errors.file && (
              <p className="text-cyber-red text-sm mt-2 flex items-start">
                <AlertCircle className="w-4 h-4 mr-1 flex-shrink-0 mt-0.5" />
                <span>{errors.file}</span>
              </p>
            )}
          </div>
        )}

        {/* Scan Configuration */}
        {(isFullScan || isJsUrlsScan) && (
        <div className="cyber-card p-3 sm:p-5 lg:p-6 mb-4 sm:mb-6">
          <div className="flex items-center space-x-3 mb-4 sm:mb-6">
            <div className="p-1.5 sm:p-2 bg-cyber-purple/20 rounded-lg flex-shrink-0">
              <Settings className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-purple" />
            </div>
            <h2 className="text-lg sm:text-xl font-semibold text-white">Configuration</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Parallel Processes
              </label>
              <input
                type="number"
                name="parallel"
                value={formData.parallel}
                onChange={handleInputChange}
                min="1"
                max="10"
                className={`cyber-input w-full ${errors.parallel ? 'border-cyber-red' : ''}`}
              />
              {errors.parallel && (
                <p className="text-cyber-red text-sm mt-1">{errors.parallel}</p>
              )}
              <p className="text-gray-500 text-xs mt-1">{isJsUrlsScan ? 'Max parallel JS URL downloads (1-10)' : 'Max parallel URL scans (1-10)'}</p>
            </div>

            {isFullScan && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Concurrency
              </label>
              <input
                type="number"
                name="concurrency"
                value={formData.concurrency}
                onChange={handleInputChange}
                min="1"
                max="10"
                className={`cyber-input w-full ${errors.concurrency ? 'border-cyber-red' : ''}`}
              />
              {errors.concurrency && (
                <p className="text-cyber-red text-sm mt-1">{errors.concurrency}</p>
              )}
              <p className="text-gray-500 text-xs mt-1">Concurrency per URL (1-10)</p>
            </div>
            )}

            {isFullScan && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Crawl Depth
              </label>
              <input
                type="number"
                name="depth"
                value={formData.depth}
                onChange={handleInputChange}
                min="0"
                max="100"
                className={`cyber-input w-full ${errors.depth ? 'border-cyber-red' : ''}`}
              />
              {errors.depth && (
                <p className="text-cyber-red text-sm mt-1">{errors.depth}</p>
              )}
              <p className="text-gray-500 text-xs mt-1">Max recursion depth (0 for infinite, default 1)</p>
            </div>
            )}

            {isFullScan && (
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Request Delay (seconds)
              </label>
              <input
                type="number"
                name="delay"
                value={formData.delay}
                onChange={handleInputChange}
                min="0"
                max="60"
                className={`cyber-input w-full ${errors.delay ? 'border-cyber-red' : ''}`}
              />
              {errors.delay && (
                <p className="text-cyber-red text-sm mt-1">{errors.delay}</p>
              )}
              <p className="text-gray-500 text-xs mt-1">Delay between requests to same domain (0-60s)</p>
            </div>
            )}
          </div>
        </div>
        )}

        {/* Advanced Configuration */}
        {(isFullScan || isJsUrlsScan) && (
        <div className="cyber-card p-3 sm:p-5 lg:p-6 mb-4 sm:mb-6">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center space-x-3 w-full text-left touch-manipulation"
          >
            <div className="p-1.5 sm:p-2 bg-cyber-yellow/20 rounded-lg flex-shrink-0">
              <Shield className="w-4 h-4 sm:w-5 sm:h-5 text-cyber-yellow" />
            </div>
            <h2 className="text-lg sm:text-xl font-semibold text-white flex-1">Advanced</h2>
            {showAdvanced ? (
              <ChevronDown className="w-5 h-5 text-gray-400" />
            ) : (
              <ChevronRight className="w-5 h-5 text-gray-400" />
            )}
          </button>

          {showAdvanced && (
            <div className="mt-4 sm:mt-6 space-y-4 sm:space-y-6">
              {/* Cookie */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Cookie
                </label>
                <input
                  type="text"
                  name="cookie"
                  value={formData.cookie}
                  onChange={handleInputChange}
                  placeholder="e.g., sessionId=abc123; token=xyz789"
                  className="cyber-input w-full font-mono text-xs sm:text-sm"
                />
                <p className="text-gray-500 text-xs mt-1">Cookie string to send with scan requests</p>
              </div>

              {/* Custom Headers */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Custom Headers
                </label>
                <div className="space-y-2">
                  {formData.headers.map((header, index) => (
                    <div key={index} className="flex items-center space-x-2">
                      <input
                        type="text"
                        value={header}
                        onChange={(e) => {
                          const newHeaders = [...formData.headers];
                          newHeaders[index] = e.target.value;
                          setFormData(prev => ({ ...prev, headers: newHeaders }));
                        }}
                        placeholder="e.g., Authorization: Bearer token123"
                        className="cyber-input flex-1 font-mono text-xs sm:text-sm"
                      />
                      {formData.headers.length > 1 && (
                        <button
                          type="button"
                          onClick={() => {
                            const newHeaders = formData.headers.filter((_, i) => i !== index);
                            setFormData(prev => ({ ...prev, headers: newHeaders }));
                          }}
                          className="p-2 hover:bg-cyber-red/20 rounded-lg transition-colors touch-manipulation flex-shrink-0"
                        >
                          <X className="w-4 h-4 text-cyber-red" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => setFormData(prev => ({ ...prev, headers: [...prev.headers, ''] }))}
                  className="mt-2 flex items-center space-x-1 text-cyber-blue text-xs sm:text-sm hover:text-cyber-blue/80 transition-colors touch-manipulation"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Header</span>
                </button>
                <p className="text-gray-500 text-xs mt-1">Custom HTTP headers to send with scan requests</p>
              </div>
            </div>
          )}
        </div>
        )}

        {/* Submit */}
        {errors.submit && (
          <div className="cyber-card p-3 sm:p-5 lg:p-6 mb-4 sm:mb-6 border-cyber-red">
            <div className="flex items-center space-x-3 text-cyber-red">
              <AlertCircle className="w-5 h-5 flex-shrink-0" />
              <p className="text-sm sm:text-base">{errors.submit}</p>
            </div>
          </div>
        )}

        <div className="flex flex-col-reverse sm:flex-row sm:items-center sm:justify-between gap-3 mobile-sticky-actions sm:static sm:m-0 sm:p-0 sm:bg-transparent sm:border-0 sm:backdrop-blur-0">
          <button
            type="button"
            onClick={() => setSelectedScanType('')}
            className="cyber-button-secondary w-full sm:w-auto justify-center"
          >
            Back
          </button>
          <button
            type="submit"
            disabled={loading}
            className="cyber-button-primary flex items-center justify-center space-x-2 w-full sm:w-auto"
          >
            {loading ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-cyber-dark"></div>
                <span>Creating...</span>
              </>
            ) : (
              <>
                <Plus className="w-4 h-4" />
                <span>Create Scan</span>
              </>
            )}
          </button>
        </div>
      </form>
      )}
    </div>
  );
};

export default CreateScan;
