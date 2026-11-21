// Επεξεργαστής Markdown: ζωντανή προεπισκόπηση (από τον server), εργαλεία μορφοποίησης, Ctrl+S.
(function () {
  var ta = document.getElementById('md'), pv = document.getElementById('preview'), form = document.getElementById('mdform'); if (!ta) return;
  var timer = null, seq = 0;
  function math() {                                  // τύποι με το τοπικό KaTeX (αν φορτώθηκε)
    if (!window.renderMathInElement) return;
    try { renderMathInElement(pv, {delimiters: [{left: '$$', right: '$$', display: true}, {left: '$', right: '$', display: false}], throwOnError: false, ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']}); } catch (e) { /* μένουν ως κείμενο */ }
  }
  function render() {
    var my = ++seq, fd = new FormData(); fd.append('md', ta.value);
    fetch('/docs/render', {method: 'POST', body: fd}).then(function (r) { return r.text(); }).then(function (h) { if (my === seq) { pv.innerHTML = h; math(); } });
  }
  function later() { clearTimeout(timer); timer = setTimeout(render, 350); }
  ta.addEventListener('input', later); render();
  function edit(fn) { var s = ta.selectionStart, e = ta.selectionEnd, v = ta.value; var r = fn(v.slice(0, s), v.slice(s, e), v.slice(e)); ta.value = r[0]; ta.selectionStart = r[1]; ta.selectionEnd = r[2]; ta.focus(); later(); }
  document.querySelectorAll('[data-wrap]').forEach(function (b) { b.addEventListener('click', function () { var w = b.dataset.wrap; edit(function (a, m, z) { return [a + w + m + w + z, a.length + w.length, a.length + w.length + m.length]; }); }); });
  document.querySelectorAll('[data-prefix]').forEach(function (b) { b.addEventListener('click', function () { var p = b.dataset.prefix; edit(function (a, m, z) { var ls = a.lastIndexOf('\n') + 1; var out = a.slice(0, ls) + p + a.slice(ls) + m + z; return [out, a.length + p.length, a.length + p.length + m.length]; }); }); });
  document.querySelectorAll('[data-insert]').forEach(function (b) { b.addEventListener('click', function () { var t = b.dataset.insert.replace(/\\n/g, '\n').replace(/\\\\/g, '\\'); edit(function (a, m, z) { return [a + t + z, a.length + t.length, a.length + t.length]; }); }); });
  function img(sol) { var n = parseInt(document.getElementById('qimg').value, 10); if (!n) return; var t = '\n\n![](/crop/' + n + '.jpg' + (sol ? '?sol=1' : '') + ')\n\n'; edit(function (a, m, z) { return [a + t + z, a.length + t.length, a.length + t.length]; }); }
  document.getElementById('addimg').addEventListener('click', function () { img(false); });
  document.getElementById('addsol').addEventListener('click', function () { img(true); });
  document.addEventListener('keydown', function (e) { if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); form.submit(); } });
})();
