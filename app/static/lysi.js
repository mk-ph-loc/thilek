// Σελίδα λύσης: καρτέλες, αντιγραφή σε Markdown (clipboard ή εφεδρικό textarea για http στο LAN) και απόδοση τύπων με το τοπικό KaTeX.
(function () {
  var root = document.querySelector('.lysi'); if (!root) return;
  function done(btn, ok) { var t = btn.textContent; btn.textContent = ok ? '✔ αντιγράφηκε' : '✖ αποτυχία'; setTimeout(function () { btn.textContent = t; }, 1500); }
  function fallback(text, btn) {                    // όχι secure context (http): textarea + execCommand('copy')
    var ta = document.createElement('textarea'); ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.top = '-1000px'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.focus(); ta.select(); var ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    document.body.removeChild(ta); done(btn, ok);
  }
  function copy(text, btn) {
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(function () { done(btn, true); }, function () { fallback(text, btn); });
    else fallback(text, btn);
  }
  root.querySelectorAll('button[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () { var src = document.getElementById(b.dataset.copy); if (src) copy(src.value, b); });
  });
  var tabs = root.querySelectorAll('.ltab'), panels = root.querySelectorAll('[data-panel]');
  function show(k) {
    var found = false; panels.forEach(function (p) { if (p.dataset.panel === k) found = true; });
    if (!found) k = tabs.length ? tabs[0].dataset.tab : '';
    panels.forEach(function (p) { p.hidden = p.dataset.panel !== k; });
    tabs.forEach(function (t) { t.classList.toggle('on', t.dataset.tab === k); });
  }
  tabs.forEach(function (t) { t.addEventListener('click', function (e) { e.preventDefault(); show(t.dataset.tab); history.replaceState(null, '', '#t-' + t.dataset.tab); }); });
  show((location.hash || '').replace('#t-', ''));
  if (window.renderMathInElement) {
    try {
      renderMathInElement(root, {delimiters: [{left: '$$', right: '$$', display: true}, {left: '$', right: '$', display: false}, {left: '\\(', right: '\\)', display: false}, {left: '\\[', right: '\\]', display: true}],
        throwOnError: false, ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'option']});
    } catch (e) { /* οι τύποι μένουν ως κείμενο LaTeX */ }
  }
})();
