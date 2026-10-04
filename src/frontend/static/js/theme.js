// Apply the saved theme before paint on both the dashboard and sign-in page.
document.documentElement.setAttribute('data-theme', localStorage.getItem('fp_theme') === 'dark' ? 'dark' : 'light');
function updateThemeUI() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const sun = document.getElementById('themeIconSun'), moon = document.getElementById('themeIconMoon');
  if (sun) sun.style.display = dark ? 'inline-block' : 'none';
  if (moon) moon.style.display = dark ? 'none' : 'inline-block';
  const badge = document.getElementById('themeBadge');
  if (badge) { badge.textContent = dark ? 'Dark' : 'Light'; badge.className = 'theme-badge ' + (dark ? 'dark' : 'light'); }
  document.querySelectorAll('[data-theme-toggle]').forEach(button => {
    button.setAttribute('aria-label', 'Switch to ' + (dark ? 'light' : 'dark') + ' theme');
    button.setAttribute('aria-pressed', String(dark));
  });
}
function toggleTheme() {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('fp_theme', next);
  updateThemeUI();
}
document.addEventListener('DOMContentLoaded', updateThemeUI);
