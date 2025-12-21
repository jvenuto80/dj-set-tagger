import { useState } from 'react'
import { 
  X, 
  Search, 
  Image, 
  Link, 
  Loader2, 
  Check,
  ExternalLink
} from 'lucide-react'
import { searchCoverArtByQuery } from '../api'
import ProgressButton from './ProgressButton'

/**
 * Modal for searching and selecting cover art
 * 
 * @param {Object} props
 * @param {boolean} props.isOpen - Whether the modal is open
 * @param {function} props.onClose - Function to close the modal
 * @param {function} props.onSelect - Function called with selected cover URL
 * @param {string} props.defaultQuery - Default search query
 */
export default function CoverArtModal({ isOpen, onClose, onSelect, defaultQuery = '' }) {
  const [activeTab, setActiveTab] = useState('search') // 'search' or 'url'
  const [searchQuery, setSearchQuery] = useState(defaultQuery)
  const [directUrl, setDirectUrl] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const [searchResults, setSearchResults] = useState([])
  const [selectedUrl, setSelectedUrl] = useState(null)
  const [previewError, setPreviewError] = useState({})

  if (!isOpen) return null

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    
    setIsSearching(true)
    setSearchResults([])
    setSelectedUrl(null)
    setPreviewError({})
    
    try {
      const results = await searchCoverArtByQuery(searchQuery)
      setSearchResults(results || [])
    } catch (error) {
      console.error('Cover art search error:', error)
    } finally {
      setIsSearching(false)
    }
  }

  const handleSelectFromSearch = (url) => {
    setSelectedUrl(url)
    setDirectUrl('')
  }

  const handleSelectFromUrl = () => {
    if (directUrl.trim()) {
      setSelectedUrl(directUrl.trim())
      setSearchResults([])
    }
  }

  const handleApply = () => {
    if (selectedUrl) {
      onSelect(selectedUrl)
      onClose()
    }
  }

  const handleImageError = (url) => {
    setPreviewError(prev => ({ ...prev, [url]: true }))
  }

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-3xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <Image className="w-5 h-5 text-primary-500" />
            <h2 className="text-lg font-semibold">Select Cover Art</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-700 rounded-lg"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          <button
            onClick={() => setActiveTab('search')}
            className={`flex-1 px-4 py-3 text-sm font-medium flex items-center justify-center gap-2 ${
              activeTab === 'search'
                ? 'text-primary-400 border-b-2 border-primary-500 bg-gray-700/30'
                : 'text-gray-400 hover:text-gray-300'
            }`}
          >
            <Search className="w-4 h-4" />
            Search Google
          </button>
          <button
            onClick={() => setActiveTab('url')}
            className={`flex-1 px-4 py-3 text-sm font-medium flex items-center justify-center gap-2 ${
              activeTab === 'url'
                ? 'text-primary-400 border-b-2 border-primary-500 bg-gray-700/30'
                : 'text-gray-400 hover:text-gray-300'
            }`}
          >
            <Link className="w-4 h-4" />
            Paste URL
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {activeTab === 'search' && (
            <div className="space-y-4">
              {/* Search Input */}
              <div className="flex gap-2">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                    placeholder="Search for album cover..."
                    className="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                </div>
                <ProgressButton
                  onClick={handleSearch}
                  isLoading={isSearching}
                  loadingText="Searching..."
                  icon={<Search className="w-4 h-4" />}
                  variant="primary"
                >
                  Search
                </ProgressButton>
              </div>

              {/* Results Grid */}
              {searchResults.length > 0 ? (
                <div className="max-h-[400px] overflow-y-auto pr-2">
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
                  {searchResults.map((cover, index) => (
                    <button
                      key={cover.url || index}
                      onClick={() => handleSelectFromSearch(cover.url)}
                      className={`relative aspect-square rounded-lg overflow-hidden border-2 transition-all ${
                        selectedUrl === cover.url
                          ? 'border-primary-500 ring-2 ring-primary-500/50'
                          : 'border-gray-600 hover:border-gray-500'
                      }`}
                    >
                      {previewError[cover.url] ? (
                        <div className="w-full h-full bg-gray-700 flex items-center justify-center">
                          <Image className="w-8 h-8 text-gray-500" />
                        </div>
                      ) : (
                        <img
                          src={cover.url}
                          alt={cover.title || 'Cover art'}
                          className="w-full h-full object-cover"
                          onError={() => handleImageError(cover.url)}
                        />
                      )}
                      {selectedUrl === cover.url && (
                        <div className="absolute inset-0 bg-primary-500/30 flex items-center justify-center">
                          <Check className="w-8 h-8 text-white" />
                        </div>
                      )}
                      {cover.source && (
                        <div className="absolute bottom-0 left-0 right-0 bg-black/70 text-xs p-1 truncate">
                          {cover.source}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
                </div>
              ) : isSearching ? (
                <div className="text-center py-12 text-gray-400">
                  <Loader2 className="w-8 h-8 animate-spin mx-auto mb-2" />
                  Searching for cover art...
                </div>
              ) : searchQuery && !isSearching ? (
                <div className="text-center py-12 text-gray-400">
                  <Image className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  No results found. Try a different search term.
                </div>
              ) : (
                <div className="text-center py-12 text-gray-400">
                  <Search className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  Enter a search term to find cover art
                </div>
              )}
            </div>
          )}

          {activeTab === 'url' && (
            <div className="space-y-4">
              {/* URL Input */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">
                  Image URL
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={directUrl}
                    onChange={(e) => setDirectUrl(e.target.value)}
                    placeholder="https://example.com/cover.jpg"
                    className="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg focus:outline-none focus:border-primary-500"
                  />
                  <button
                    onClick={handleSelectFromUrl}
                    disabled={!directUrl.trim()}
                    className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg"
                  >
                    Preview
                  </button>
                </div>
                <p className="text-xs text-gray-500 mt-1">
                  Paste a direct link to an image file (JPG, PNG, etc.)
                </p>
              </div>

              {/* Preview */}
              {selectedUrl && activeTab === 'url' && (
                <div className="mt-4">
                  <label className="block text-sm text-gray-400 mb-2">Preview</label>
                  <div className="inline-block relative">
                    <img
                      src={selectedUrl}
                      alt="Cover preview"
                      className="max-w-[300px] max-h-[300px] rounded-lg border border-gray-600"
                      onError={() => handleImageError(selectedUrl)}
                    />
                    {previewError[selectedUrl] && (
                      <div className="absolute inset-0 bg-gray-700 rounded-lg flex items-center justify-center">
                        <div className="text-center text-gray-400">
                          <Image className="w-8 h-8 mx-auto mb-2" />
                          <p className="text-sm">Failed to load image</p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-700 bg-gray-800/50">
          <div className="text-sm text-gray-400">
            {selectedUrl ? (
              <span className="flex items-center gap-2">
                <Check className="w-4 h-4 text-green-400" />
                Image selected
              </span>
            ) : (
              'Select an image to use as cover art'
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
            >
              Cancel
            </button>
            <button
              onClick={handleApply}
              disabled={!selectedUrl}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500 rounded-lg flex items-center gap-2"
            >
              <Check className="w-4 h-4" />
              Use This Cover
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
