/* Πίνακες: ρυθμιζόμενο πλάτος στηλών (σύρσιμο ή βέλη στη λαβή), οριζόντια κύλιση, αποθήκευση ανά σελίδα στον browser. */
(function () {
  var KEY = 'thilek-colw:' + location.pathname, MIN = 48;
  function load() { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } }
  function save(o) { try { localStorage.setItem(KEY, JSON.stringify(o)); } catch (e) {} }
  var store = load();
  var st = document.createElement('style');
  st.textContent = '.tscroll{overflow-x:auto;max-width:100%}table[data-rsz]{table-layout:fixed;max-width:none}table[data-rsz] td,table[data-rsz] th{overflow-wrap:anywhere}' +
    '.rsz{position:absolute;top:0;right:0;width:9px;height:100%;cursor:col-resize;user-select:none;touch-action:none;z-index:2}.rsz:hover,.rsz:focus,.rsz.on{background:rgba(31,58,104,.35);outline:0}' +
    'th.hasrsz{position:sticky;padding-right:12px}.rszreset{font-size:.75rem;margin:.1rem 0;cursor:pointer;background:none;border:0;color:var(--muted,#667);text-decoration:underline}';
  document.head.appendChild(st);
  function init(t, ti) {
    if (t.dataset.rsz || t.closest('.nosz')) return;
    var hr = t.querySelector('tr'); if (!hr) return;
    var ths = Array.prototype.slice.call(hr.children);
    if (!ths.length || ths.some(function (c) { return c.tagName !== 'TH' || c.colSpan > 1; })) return;
    if (!t.closest('.scroll,.tscroll')) { var w = document.createElement('div'); w.className = 'tscroll'; t.parentNode.insertBefore(w, t); w.appendChild(t); }
    var key = ti + ':' + ths.map(function (h) { return h.textContent.trim(); }).join('|').slice(0, 90), ws = null;
    function apply() {
      t.dataset.rsz = '1'; var sum = 0;
      ths.forEach(function (h, i) { h.style.width = ws[i] + 'px'; h.style.minWidth = ws[i] + 'px'; sum += ws[i]; });
      t.style.width = sum + 'px';
    }
    function freeze() { if (!ws) { ws = ths.map(function (h) { return Math.round(h.getBoundingClientRect().width); }); apply(); } }
    function reset() {
      ws = null; delete t.dataset.rsz; t.style.width = ''; ths.forEach(function (h) { h.style.width = ''; h.style.minWidth = ''; });
      delete store[key]; save(store); if (btn) btn.hidden = true;
    }
    var btn = document.createElement('button'); btn.type = 'button'; btn.className = 'rszreset'; btn.textContent = '↔ επαναφορά πλάτους στηλών'; btn.hidden = true; btn.onclick = reset;
    (t.closest('.scroll,.tscroll') || t).insertAdjacentElement('afterend', btn);
    function changed() { btn.hidden = false; store[key] = ws; save(store); }
    ths.forEach(function (h, i) {
      if (getComputedStyle(h).position === 'static') h.style.position = 'relative';
      h.classList.add('hasrsz');
      var g = document.createElement('span'); g.className = 'rsz'; g.tabIndex = 0; g.setAttribute('role', 'separator'); g.setAttribute('aria-orientation', 'vertical'); g.title = 'Σύρε για πλάτος στήλης· διπλό κλικ για επαναφορά';
      g.addEventListener('click', function (e) { e.stopPropagation(); });
      g.addEventListener('dblclick', function (e) { e.stopPropagation(); reset(); });
      g.addEventListener('pointerdown', function (e) {
        e.preventDefault(); e.stopPropagation(); freeze(); var x0 = e.clientX, w0 = ws[i]; g.setPointerCapture(e.pointerId); g.classList.add('on');
        function mv(ev) { ws[i] = Math.max(MIN, Math.round(w0 + ev.clientX - x0)); apply(); }
        function up() { g.classList.remove('on'); g.removeEventListener('pointermove', mv); g.removeEventListener('pointerup', up); g.removeEventListener('pointercancel', up); changed(); }
        g.addEventListener('pointermove', mv); g.addEventListener('pointerup', up); g.addEventListener('pointercancel', up);
      });
      g.addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return; e.preventDefault(); e.stopPropagation(); freeze();
        ws[i] = Math.max(MIN, ws[i] + (e.key === 'ArrowRight' ? 12 : -12)); apply(); changed();
      });
      h.appendChild(g);
    });
    var saved = store[key]; if (saved && saved.length === ths.length) { ws = saved.map(function (n) { return Math.max(MIN, +n || MIN); }); apply(); btn.hidden = false; }
  }
  function run() { Array.prototype.forEach.call(document.querySelectorAll('table'), init); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
})();
