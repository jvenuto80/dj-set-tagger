/**
 * Tauri integration helpers.
 *
 * Detects whether the app is running inside Tauri (native) or in a browser
 * (Docker/dev mode) and provides native feature wrappers.
 */

/** True when running inside the Tauri WebView */
export const isTauri = () => Boolean(window.__TAURI_INTERNALS__);

/**
 * Show a native macOS notification (falls back to browser Notification API).
 */
export async function notify(title, body) {
  if (isTauri()) {
    try {
      const { sendNotification, isPermissionGranted, requestPermission } =
        await import('@tauri-apps/plugin-notification');
      let granted = await isPermissionGranted();
      if (!granted) {
        const perm = await requestPermission();
        granted = perm === 'granted';
      }
      if (granted) {
        sendNotification({ title, body });
      }
    } catch (e) {
      console.warn('Notification plugin unavailable:', e);
    }
  } else if ('Notification' in window) {
    if (Notification.permission === 'granted') {
      new Notification(title, { body });
    } else if (Notification.permission !== 'denied') {
      const perm = await Notification.requestPermission();
      if (perm === 'granted') new Notification(title, { body });
    }
  }
}

/**
 * Open a native folder picker dialog.
 * Returns the selected path string or null.
 */
export async function pickFolder() {
  if (isTauri()) {
    try {
      const { open } = await import('@tauri-apps/plugin-dialog');
      const selected = await open({ directory: true, multiple: false });
      return selected || null;
    } catch (e) {
      console.warn('Dialog plugin unavailable:', e);
      return null;
    }
  }
  // Browser fallback: no native folder picker
  return null;
}

/**
 * Invoke a Tauri command (no-op in browser mode).
 */
export async function invoke(cmd, args = {}) {
  if (isTauri()) {
    const { invoke: tauriInvoke } = await import('@tauri-apps/api/core');
    return tauriInvoke(cmd, args);
  }
  return null;
}
