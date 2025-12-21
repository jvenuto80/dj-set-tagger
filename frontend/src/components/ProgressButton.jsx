import { Loader2 } from 'lucide-react'

/**
 * A button with an integrated progress bar for long-running operations.
 * Shows a subtle animated progress bar inside the button when loading.
 * 
 * @param {Object} props
 * @param {boolean} props.isLoading - Whether the button is in loading state
 * @param {function} props.onClick - Click handler
 * @param {boolean} props.disabled - Whether the button is disabled
 * @param {string} props.className - Additional CSS classes
 * @param {React.ReactNode} props.children - Button content when not loading
 * @param {string} props.loadingText - Text to show when loading (optional)
 * @param {React.ReactNode} props.icon - Icon to show when not loading (optional)
 * @param {string} props.variant - Button variant: 'primary' | 'success' | 'danger' | 'warning' | 'secondary' (default: 'primary')
 * @param {number} props.progress - Optional progress value 0-100 for determinate progress
 */
export default function ProgressButton({
  isLoading = false,
  onClick,
  disabled = false,
  className = '',
  children,
  loadingText,
  icon,
  variant = 'primary',
  progress = null,
}) {
  const variantClasses = {
    primary: 'bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700',
    success: 'bg-green-600 hover:bg-green-700 disabled:bg-gray-700',
    danger: 'bg-red-600 hover:bg-red-700 disabled:bg-gray-700',
    warning: 'bg-amber-600 hover:bg-amber-700 disabled:bg-gray-700',
    secondary: 'bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800',
  }

  const progressBarColors = {
    primary: 'bg-primary-400',
    success: 'bg-green-400',
    danger: 'bg-red-400',
    warning: 'bg-amber-400',
    secondary: 'bg-gray-400',
  }

  return (
    <button
      onClick={onClick}
      disabled={disabled || isLoading}
      className={`relative overflow-hidden px-4 py-2 rounded-lg flex items-center justify-center gap-2 disabled:text-gray-500 transition-colors ${variantClasses[variant]} ${className}`}
    >
      {/* Progress bar overlay */}
      {isLoading && (
        <div className="absolute inset-0 overflow-hidden">
          {progress !== null ? (
            // Determinate progress bar
            <div 
              className={`absolute inset-y-0 left-0 ${progressBarColors[variant]} opacity-30 transition-all duration-300`}
              style={{ width: `${progress}%` }}
            />
          ) : (
            // Indeterminate animated progress bar
            <div className={`absolute inset-y-0 w-1/3 ${progressBarColors[variant]} opacity-30 animate-progress-slide`} />
          )}
        </div>
      )}
      
      {/* Button content */}
      <span className="relative z-10 flex items-center gap-2">
        {isLoading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            {loadingText || 'Processing...'}
          </>
        ) : (
          <>
            {icon}
            {children}
          </>
        )}
      </span>
    </button>
  )
}
