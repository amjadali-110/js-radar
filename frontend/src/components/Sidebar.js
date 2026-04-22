import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Search,
  Activity,
  Plus,
  Menu,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';
import Logo from './Logo';

const Sidebar = ({ isOpen, onToggle, collapsed, onCollapse }) => {
  const location = useLocation();

  // On mobile, always show expanded sidebar regardless of collapsed state
  const [isMobile, setIsMobile] = useState(window.innerWidth < 1024);
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 1024);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  const effectiveCollapsed = isMobile ? false : collapsed;

  const menuItems = [
    { path: '/dashboard', icon: Activity, label: 'Dashboard' },
    { path: '/scans', icon: Search, label: 'Scans' },
    { path: '/scans/new', icon: Plus, label: 'New Scan' },
  ];


  const isActive = (path) => {
    return location.pathname === path ||
           (path === '/scans' && location.pathname.startsWith('/scans') && location.pathname !== '/scans/new');
  };

  const handleLinkClick = () => {
    if (window.innerWidth < 1024) {
      onToggle();
    }
  };

  const handleCollapseClick = () => {
    if (window.innerWidth < 1024) {
      onToggle();
      return;
    }
    onCollapse();
  };

  return (
    <>
      {/* Mobile Menu Button */}
      {!isOpen && (
        <button
          onClick={onToggle}
          className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-cyber-gray/90 border border-cyber-light rounded-lg text-white hover:bg-cyber-light transition-colors shadow-lg shadow-cyan-500/40"
          aria-label="Open menu"
        >
          <Menu className="w-6 h-6" />
        </button>
      )}

      {/* Overlay for mobile */}
      {isOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-30 backdrop-blur-sm"
          onClick={onToggle}
        />
      )}

      {/* Sidebar */}
      <div className={`
        fixed lg:static inset-y-0 left-0 z-40
        ${effectiveCollapsed ? 'w-64 lg:w-16' : 'w-64'} bg-cyber-gray/95 border-r border-cyber-light flex flex-col cyber-chrome
        transform transition-all duration-300 ease-in-out
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Logo */}
        <div className={`${effectiveCollapsed ? 'p-3' : 'p-4 lg:p-6'} border-b border-cyber-light relative overflow-hidden`}>
          <div className="absolute inset-0 pointer-events-none opacity-40 bg-[radial-gradient(circle_at_0_0,rgba(0,212,255,0.35),transparent_55%),radial-gradient(circle_at_100%_0,rgba(165,94,234,0.35),transparent_55%)]" />
          <div className={`flex items-center ${effectiveCollapsed ? 'justify-center' : 'space-x-3'} relative`}>
            <div className={`${effectiveCollapsed ? 'p-0.5' : 'p-0.5'} bg-gradient-to-br from-cyber-blue to-cyber-green rounded-xl flex-shrink-0 shadow-lg shadow-cyan-400/40`}>
              <Logo className={`${effectiveCollapsed ? 'w-9 h-9' : 'w-10 h-10 lg:w-11 lg:h-11'}`} />
            </div>
            {!effectiveCollapsed && (
              <div className="min-w-0">
                <h1 className="text-lg lg:text-xl font-bold text-white truncate tracking-tight">JS Radar</h1>
                <p className="text-[11px] text-cyber-blue/80 uppercase tracking-[0.18em]">
                  Security Analysis
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Navigation */}
        <nav className={`flex-1 ${effectiveCollapsed ? 'p-2' : 'p-3 lg:p-4'} overflow-y-auto`}>
          <div className="space-y-1 lg:space-y-2">
            {menuItems.map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={handleLinkClick}
                  title={effectiveCollapsed ? item.label : ''}
                  className={`flex items-center ${effectiveCollapsed ? 'justify-center px-2 py-2.5' : 'space-x-3 px-3 lg:px-4 py-2.5 lg:py-3'} rounded-lg transition-all duration-200 ${
                    isActive(item.path)
                      ? 'bg-cyber-blue text-cyber-dark font-medium'
                      : 'text-gray-300 hover:bg-cyber-light hover:text-white active:bg-cyber-light'
                  }`}
                >
                  <Icon className="w-5 h-5 flex-shrink-0" />
                  {!effectiveCollapsed && <span className="truncate">{item.label}</span>}
                </Link>
              );
            })}
          </div>

        </nav>

        {/* Collapse button + Version */}
        <div className="border-t border-cyber-light">
          <button
            onClick={handleCollapseClick}
            className={`w-full flex items-center ${effectiveCollapsed ? 'justify-center px-2' : 'space-x-3 px-3 lg:px-4'} py-3 text-gray-400 hover:text-white hover:bg-cyber-light transition-colors`}
            title={effectiveCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {effectiveCollapsed ? <ChevronRight className="w-4 h-4" /> : (
              <>
                <ChevronLeft className="w-4 h-4 flex-shrink-0" />
                <span className="text-sm truncate">Collapse</span>
              </>
            )}
          </button>
          <div className={`${effectiveCollapsed ? 'px-1 py-2' : 'px-4 py-3 pb-4'} border-t border-cyber-light`}>
            {effectiveCollapsed ? (
              <a
                href="https://www.linkedin.com/in/amjadali110/"
                target="_blank"
                rel="noopener noreferrer"
                title="v1.0.0 | Built by Amjad Ali"
                className="flex justify-center group"
              >
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyber-blue/10 to-cyber-purple/10 border border-cyber-light/50 group-hover:border-cyber-blue/40 flex items-center justify-center transition-all duration-200">
                  <span className="text-[9px] font-bold text-gray-500 group-hover:text-cyber-blue transition-colors font-mono">1.0</span>
                </div>
              </a>
            ) : (
              <div className="flex items-center justify-center gap-2 whitespace-nowrap">
                <span className="text-[10px] leading-none text-cyber-blue/70 font-mono bg-cyber-blue/10 px-2 py-0.5 rounded-full">v1.0.0</span>
                <span className="text-[10px] leading-none text-gray-600">&#183;</span>
                <span className="text-[11px] leading-none text-gray-400">Built by <a
                  href="https://www.linkedin.com/in/amjadali110/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-medium text-gray-400 hover:text-cyber-blue transition-colors duration-200"
                >Amjad Ali</a></span>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
};

export default Sidebar;
