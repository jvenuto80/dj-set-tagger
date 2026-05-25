import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { 
  Home, 
  Music, 
  FolderSearch, 
  Settings, 
  Disc3,
  Radio,
  Copy,
  Search,
  Sparkles,
  Menu,
  X
} from 'lucide-react'

const navItems = [
  { path: '/', icon: Home, label: 'Dashboard' },
  { path: '/tracks', icon: Music, label: 'Tracks' },
  { path: '/scan', icon: FolderSearch, label: 'Scan' },
  { path: '/series', icon: Radio, label: 'Series' },
  { path: '/duplicates', icon: Copy, label: 'Duplicates' },
  { path: '/library', icon: Search, label: 'Library Scan' },
  { path: '/review', icon: Sparkles, label: 'Review Queue' },
  { path: '/settings', icon: Settings, label: 'Settings' },
]

function Layout({ children }) {
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="h-screen flex">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-64 bg-gray-800 border-r border-gray-700 flex flex-col
        transform transition-transform duration-200 ease-in-out
        lg:relative lg:translate-x-0
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3" onClick={() => setSidebarOpen(false)}>
            <Disc3 className="w-8 h-8 text-primary-500" />
            <span className="text-xl font-bold">SetList</span>
          </Link>
          <button 
            className="lg:hidden text-gray-400 hover:text-white"
            onClick={() => setSidebarOpen(false)}
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        
        <nav className="p-4 flex-1">
          <ul className="space-y-2">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path
              const Icon = item.icon
              
              return (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    onClick={() => setSidebarOpen(false)}
                    className={`flex items-center gap-3 px-4 py-2 rounded-lg transition-colors ${
                      isActive
                        ? 'bg-primary-600 text-white'
                        : 'text-gray-300 hover:bg-gray-700'
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    {item.label}
                  </Link>
                </li>
              )
            })}
          </ul>
        </nav>
        
        <div className="p-4 border-t border-gray-700">
          <div className="text-xs text-gray-500 text-center">
            SetList v1.0 beta
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto min-w-0 h-screen">
        {/* Mobile header */}
        <div className="lg:hidden sticky top-0 z-30 bg-gray-900 border-b border-gray-700 px-4 py-3 flex items-center gap-3">
          <button 
            onClick={() => setSidebarOpen(true)}
            className="text-gray-400 hover:text-white"
          >
            <Menu className="w-6 h-6" />
          </button>
          <Disc3 className="w-5 h-5 text-primary-500" />
          <span className="font-semibold">SetList</span>
        </div>
        <div className="p-4 md:p-6">
          {children}
        </div>
      </main>
    </div>
  )
}

export default Layout
