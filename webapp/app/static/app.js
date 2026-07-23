// Initialize Mermaid diagrams in reports
if (typeof mermaid !== 'undefined') {
  mermaid.initialize({
    startOnLoad: true,
    theme: 'base',
    securityLevel: 'strict',
    themeVariables: {
      primaryColor: '#6366f1',
      primaryTextColor: '#ffffff',
      primaryBorderColor: '#4f46e5',
      secondaryColor: '#a78bfa',
      tertiaryColor: '#e0e7ff',
      lineColor: '#6b7280',
      textColor: '#171a21',
      xyChart: {
        plotColorPalette: '#6366f1,#8b5cf6,#a78bfa,#c4b5fd,#4f46e5,#818cf8'
      }
    },
    xyChart: { width: 600, height: 400, plotReservedSpacePercent: 60 }
  });
  // Re-run after htmx swaps (e.g. when report loads via fragment)
  document.addEventListener('htmx:afterSettle', function () {
    mermaid.run({ querySelector: 'pre.mermaid' }).catch(function () {});
  });
}

// Keep the live log panel pinned to the bottom unless the user scrolled up.
document.addEventListener('htmx:beforeSwap', function (evt) {
  var panel = document.getElementById('log-panel');
  if (!panel || evt.detail.target !== panel) return;
  panel.dataset.stick =
    panel.scrollHeight - panel.scrollTop - panel.clientHeight < 40 ? '1' : '';
});
document.addEventListener('htmx:afterSwap', function (evt) {
  var panel = document.getElementById('log-panel');
  if (!panel || evt.detail.target !== panel) return;
  if (panel.dataset.stick) panel.scrollTop = panel.scrollHeight;
});

// Light/dark toggle. First click switches away from the system preference;
// the choice persists in localStorage (read pre-paint by theme.js).
document.addEventListener('click', function (evt) {
  var btn = evt.target.closest('#theme-toggle');
  if (!btn) return;
  var html = document.documentElement;
  var current = html.getAttribute('data-theme');
  if (!current) {
    current = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  var next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  try { localStorage.setItem('theme', next); } catch (e) { /* ignore */ }
});

// Close the user menu when clicking anywhere else.
document.addEventListener('click', function (evt) {
  document.querySelectorAll('details.user-menu[open]').forEach(function (menu) {
    if (!menu.contains(evt.target)) menu.removeAttribute('open');
  });
});
