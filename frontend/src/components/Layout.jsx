import { Link, useLocation } from 'react-router-dom'
import { 
  Home, 
  Music, 
  FolderSearch, 
  Settings, 
  Disc3,
  Radio
} from 'lucide-react'

const navItems = [
  { path: '/', icon: Home, label: 'Dashboard' },
  { path: '/tracks', icon: Music, label: 'Tracks' },
  { path: '/scan', icon: FolderSearch, label: 'Scan' },
  { path: '/series', icon: Radio, label: 'Series' },
  { path: '/settings', icon: Settings, label: 'Settings' },
]

function Layout({ children }) {
  const location = useLocation()

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
        <div className="p-4 border-b border-gray-700">
          <Link to="/" className="flex items-center gap-3">
            <Disc3 className="w-8 h-8 text-primary-500" />
            <span className="text-xl font-bold">SetList</span>
          </Link>
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
            SetList v0.7.0 alpha
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-6">
          {children}
        </div>
      </main>
    </div>
  )
}

export default Layout
