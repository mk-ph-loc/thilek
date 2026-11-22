// 0.39: Εργαλεία αρχείων — γρήγορο φίλτρο λίστας, επιλογή εμφανιζόμενων, αυτόματη επιλογή καθώς πληκτρολογείς (χωρίς inline χειριστές: CSP)
(function () {
  var inp = document.getElementById('foFilter'); if (!inp) return;
  var labels = [].slice.call(document.querySelectorAll('.fol label'));
  var auto = document.getElementById('foAuto'), stat = document.getElementById('foStat'), autoSet = [];
  function norm(s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  var texts = labels.map(function (l) { return norm(l.textContent); });
  function box(l) { return l.querySelector('input'); }
  function refresh() {
    var shown = 0, sel = 0;
    labels.forEach(function (l) { if (!l.hidden) shown++; var b = box(l); if (b && b.checked) sel++; });
    if (stat) stat.textContent = 'εμφανίζονται ' + shown + ' από ' + labels.length + ' · επιλεγμένα ' + sel;
  }
  function apply() {
    var terms = norm(inp.value).split(/\s+/).filter(Boolean);
    labels.forEach(function (l, i) { l.hidden = !terms.every(function (t) { return texts[i].indexOf(t) >= 0; }); });
    if (auto && auto.checked) labels.forEach(function (l) {
      var b = box(l); if (!b || b.type !== 'checkbox') return; var k = autoSet.indexOf(b);
      if (terms.length && !l.hidden) { if (!b.checked) { b.checked = true; autoSet.push(b); } }
      else if (k >= 0) { b.checked = false; autoSet.splice(k, 1); }
    });
    refresh();
  }
  function setVisible(v) {
    labels.forEach(function (l) { var b = box(l); if (b && b.type === 'checkbox' && !l.hidden) { b.checked = v; var k = autoSet.indexOf(b); if (k >= 0) autoSet.splice(k, 1); } });
    refresh();
  }
  inp.addEventListener('input', apply);
  inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') e.preventDefault(); });
  if (auto) auto.addEventListener('change', function () { if (auto.checked) apply(); else autoSet = []; });
  var a = document.getElementById('foAll'), n = document.getElementById('foNone');
  if (a) a.addEventListener('click', function () { setVisible(true); });
  if (n) n.addEventListener('click', function () { setVisible(false); });
  document.addEventListener('change', function (e) { var k = autoSet.indexOf(e.target); if (k >= 0) autoSet.splice(k, 1); refresh(); });
  refresh();
})();
