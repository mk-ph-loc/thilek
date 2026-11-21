// Διαδραστικό quiz: έλεγχος τύπου Σωστό/Λάθος και πολλαπλής επιλογής, εμφάνιση απάντησης στις ελεύθερες, ανακάτεμα.
(function () {
  var root = document.getElementById('quiz'); if (!root) return;
  function items() { return Array.prototype.slice.call(root.querySelectorAll('.qi')); }
  document.getElementById('check').addEventListener('click', function () {
    var got = 0, total = 0, done = 0;
    items().forEach(function (it) {
      var kind = it.dataset.kind, ans = it.dataset.answer, pts = parseFloat(it.dataset.points) || 0;
      it.classList.remove('ok', 'bad'); var fb = it.querySelector('.fb'); if (fb) fb.hidden = false;
      if (kind === 'free') { var d = it.querySelector('details'); if (d) d.open = true; return; }
      total += pts; var sel = it.querySelector('input[type=radio]:checked');
      if (!sel) { it.classList.add('bad'); return; }
      done++; if (sel.value === ans) { got += pts; it.classList.add('ok'); } else it.classList.add('bad');
    });
    document.getElementById('score').textContent = 'Βαθμολογήσιμα: ' + got + ' / ' + total + ' μονάδες (' + done + ' απαντημένα)';
  });
  document.getElementById('reset').addEventListener('click', function () {
    items().forEach(function (it) { it.classList.remove('ok', 'bad'); it.querySelectorAll('input[type=radio]').forEach(function (r) { r.checked = false; }); var fb = it.querySelector('.fb'); if (fb) fb.hidden = true; var d = it.querySelector('details'); if (d) d.open = false; });
    document.getElementById('score').textContent = '';
  });
  function shuffle(parent, nodes) { for (var i = nodes.length - 1; i > 0; i--) { var j = Math.floor(Math.random() * (i + 1)); var t = nodes[i]; nodes[i] = nodes[j]; nodes[j] = t; } nodes.forEach(function (n) { parent.appendChild(n); }); }
  document.getElementById('shuffle').addEventListener('click', function () {
    shuffle(root, items());
    items().forEach(function (it) { var o = it.querySelector('.opts'); if (o && it.dataset.kind === 'mcq') shuffle(o, Array.prototype.slice.call(o.children)); });
    items().forEach(function (it, i) { var n = it.querySelector('.num'); if (n) n.textContent = (i + 1) + '.'; });
  });
})();
