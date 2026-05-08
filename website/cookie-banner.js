/* NEXORA — Cookie consent banner (Phase 9)
 * - Shows on first visit
 * - Stores consent in localStorage as 'nexora_cookie_consent'
 * - Two buttons: Accept (saves), Learn More (opens cookie policy)
 */
(function () {
  'use strict';
  var STORAGE_KEY = 'nexora_cookie_consent';
  var STORAGE_VERSION = '1';

  function hasConsent() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return false;
      var data = JSON.parse(raw);
      return data && data.version === STORAGE_VERSION && data.accepted === true;
    } catch (e) {
      return false;
    }
  }

  function saveConsent() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        version: STORAGE_VERSION,
        accepted: true,
        ts: new Date().toISOString()
      }));
    } catch (e) {
      /* noop — private browsing etc. */
    }
  }

  function buildBanner() {
    var banner = document.createElement('div');
    banner.id = 'nexora-cookie-banner';
    banner.setAttribute('role', 'dialog');
    banner.setAttribute('aria-live', 'polite');
    banner.setAttribute('aria-label', 'Cookie consent');
    banner.innerHTML = [
      '<div class="cb-inner">',
      '  <div class="cb-text">',
      '    🍪 We use cookies to improve your experience and analyze traffic. ',
      '    By continuing to use this site, you agree to our use of cookies.',
      '  </div>',
      '  <div class="cb-actions">',
      '    <a class="cb-link" href="/cookies.html">Learn More</a>',
      '    <button class="cb-accept" type="button">Accept</button>',
      '  </div>',
      '</div>'
    ].join('');
    return banner;
  }

  function show() {
    if (hasConsent()) return;
    if (document.getElementById('nexora-cookie-banner')) return;
    var banner = buildBanner();
    document.body.appendChild(banner);
    var btn = banner.querySelector('.cb-accept');
    if (btn) {
      btn.addEventListener('click', function () {
        saveConsent();
        banner.classList.add('cb-hide');
        setTimeout(function () { banner.remove(); }, 300);
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', show);
  } else {
    show();
  }
})();
