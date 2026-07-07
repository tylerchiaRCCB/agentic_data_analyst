// Applies the saved theme before first paint. Loaded synchronously in <head>.
(function () {
  try {
    var t = localStorage.getItem('theme');
    if (t === 'light' || t === 'dark') {
      document.documentElement.setAttribute('data-theme', t);
    }
  } catch (e) { /* private mode etc. — fall back to system preference */ }
})();
