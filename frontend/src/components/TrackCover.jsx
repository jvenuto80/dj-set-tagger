import { useState } from 'react'
import { Music } from 'lucide-react'
import { embeddedCoverUrl } from '../api'

/**
 * Track cover image with three-tier fallback:
 *   1. matchedUrl (cover URL set by a successful tracklist/Spotify match)
 *   2. embedded cover art from the audio file (via /api/covers/embedded/:id/image)
 *   3. generic music-note icon
 *
 * The embedded endpoint returns 404 when the file has no APIC/picture frame;
 * we detect that via the <img> onError handler and fall back to the icon.
 */
export default function TrackCover({ trackId, matchedUrl, alt = '', iconClassName = 'w-5 h-5 sm:w-6 sm:h-6 text-gray-400' }) {
  const [embeddedFailed, setEmbeddedFailed] = useState(false)

  if (matchedUrl) {
    return (
      <img
        src={matchedUrl}
        alt={alt}
        className="w-full h-full object-cover"
        onError={(e) => { e.currentTarget.style.display = 'none' }}
      />
    )
  }

  if (trackId && !embeddedFailed) {
    return (
      <img
        src={embeddedCoverUrl(trackId)}
        alt={alt}
        className="w-full h-full object-cover"
        onError={() => setEmbeddedFailed(true)}
      />
    )
  }

  return <Music className={iconClassName} />
}
