/* TH-ILEK 0.19.0: help ανά σελίδα, λίστες εργασιών, Mermaid, φίλτρο ερωτήσεων. Χωρίς inline JS (CSP 'self'). */
(function () {
  function ls(k, v) { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { return null; } }
  document.querySelectorAll('details.help[data-hk]').forEach(function (d) {
    var k = 'thilek.help.' + d.dataset.hk, v = ls(k), mode = document.documentElement.getAttribute('data-helpmode') || 'remember';
    if (mode === 'open') { d.open = true; return; }          // «ΠΑΝΤΑ ανοιχτή»: δεν διαβάζει ούτε γράφει μνήμη
    if (mode === 'closed') { d.open = false; return; }
    d.open = v === '1' ? true : v === '0' ? false : d.dataset.def === 'open';
    d.addEventListener('toggle', function () { ls(k, d.open ? '1' : '0'); });
  });
  document.querySelectorAll('input.ck[data-ck]').forEach(function (b) {
    var k = 'thilek.ck.' + b.dataset.ck, v = ls(k); if (v !== null) b.checked = v === '1';
    b.addEventListener('change', function () { ls(k, b.checked ? '1' : '0'); });
  });
  document.querySelectorAll('[data-act=help-reset]').forEach(function (b) {
    b.addEventListener('click', function () {
      try { Object.keys(localStorage).filter(function (x) { return x.indexOf('thilek.help.') === 0; }).forEach(function (x) { localStorage.removeItem(x); }); } catch (e) {}
      b.textContent = '✔ Έγινε επαναφορά';
    });
  });
  if (window.mermaid && document.querySelector('pre.mermaid')) {
    try {
      window.mermaid.initialize({ startOnLoad: false, theme: 'default', securityLevel: 'strict' });
      window.mermaid.run({ querySelector: 'pre.mermaid' }).catch(function (e) { console.warn('mermaid', e); });
    } catch (e) { console.warn('mermaid', e); }
  }
  function norm(s) { return s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/ς/g, 'σ'); }
  document.querySelectorAll('input[data-filter]').forEach(function (inp) {
    var items = Array.prototype.slice.call(document.querySelectorAll(inp.dataset.filter)), cnt = document.getElementById(inp.dataset.count || '');
    function run() {
      var q = norm(inp.value.trim()), n = 0;
      items.forEach(function (it) { var hit = !q || norm(it.textContent).indexOf(q) >= 0; it.style.display = hit ? '' : 'none'; if (q && hit && it.tagName === 'DETAILS') it.open = true; if (hit) n++; });
      if (cnt) cnt.textContent = q ? n + ' αποτελέσματα' : items.length + ' ερωτήσεις';
    }
    inp.addEventListener('input', run); run();
  });
  document.querySelectorAll('[data-open-all]').forEach(function (b) {
    b.addEventListener('click', function () { var o = b.dataset.openAll === '1'; document.querySelectorAll('details.adm[data-faq]').forEach(function (d) { if (d.style.display !== 'none') d.open = o; }); });
  });
})();
