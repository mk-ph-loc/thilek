// Ταξινόμηση πινάκων με κλικ στην επικεφαλίδα και πλοήγηση θεμάτων με βέλη. Χωρίς εξωτερικές βιβλιοθήκες.
(function () {
  var collator = new Intl.Collator('el', {numeric: true, sensitivity: 'base'});
  function val(td) { return (td ? td.textContent : '').trim(); }
  function num(s) { var t = s.replace(',', '.'); return /^-?\d+(\.\d+)?$/.test(t) ? parseFloat(t) : null; }
  document.querySelectorAll('table').forEach(function (tb) {
    var head = tb.rows[0]; if (!head) return;
    Array.prototype.forEach.call(head.cells, function (th, col) {
      th.classList.add('sortable'); th.title = 'Κλικ για ταξινόμηση';
      th.addEventListener('click', function () {
        var asc = th.dataset.dir !== 'asc';
        Array.prototype.forEach.call(head.cells, function (o) { o.dataset.dir = ''; var a = o.querySelector('.arr'); if (a) a.remove(); });
        th.dataset.dir = asc ? 'asc' : 'desc';
        var arr = document.createElement('span'); arr.className = 'arr'; arr.textContent = asc ? ' ▲' : ' ▼'; th.appendChild(arr);
        var rows = Array.prototype.slice.call(tb.rows, 1);
        rows.sort(function (a, b) {
          var x = val(a.cells[col]), y = val(b.cells[col]);
          if (x === '' || y === '') return x === y ? 0 : (x === '' ? 1 : -1);   // τα κενά πάντα τελευταία
          var nx = num(x), ny = num(y), r = (nx !== null && ny !== null) ? nx - ny : collator.compare(x, y);
          return asc ? r : -r;
        });
        var body = tb.tBodies[0] || tb; rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  });
  var allBoxes = document.querySelectorAll('input[data-all]');          // «επιλογή όλων» + μετρητής επιλεγμένων
  function count() {
    var n = 0, c = document.getElementById('count');
    allBoxes.forEach(function (all) { document.querySelectorAll('input[name="' + all.dataset.all + '"]').forEach(function (b) { if (b.checked) n++; }); });
    if (c) c.textContent = n;
  }
  allBoxes.forEach(function (all) {
    var boxes = function () { return document.querySelectorAll('input[name="' + all.dataset.all + '"]'); };
    all.addEventListener('click', function (e) { e.stopPropagation(); boxes().forEach(function (b) { b.checked = all.checked; }); count(); });
    boxes().forEach(function (b) { b.addEventListener('change', count); });
  });
  document.addEventListener('click', function (e) {      // αγαπημένα: ★/☆ χωρίς ανανέωση σελίδας
    var b = e.target.closest ? e.target.closest('button[data-fav]') : null; if (!b) return; e.preventDefault();
    fetch('/fav/' + b.dataset.fav, {method: 'POST'}).then(function (r) { return r.json(); }).then(function (j) {
      document.querySelectorAll('button[data-fav="' + b.dataset.fav + '"]').forEach(function (x) { x.classList.toggle('on', j.fav); x.textContent = j.fav ? '★' : '☆'; });
    });
  });
  var pv = document.createElement('div'); pv.id = 'pv'; pv.innerHTML = '<img alt="">'; document.body.appendChild(pv);       // προεπισκόπηση θέματος στο πέρασμα του ποντικιού
  var pvTimer = null, pvId = null;
  function pvMove(e) { var x = e.clientX + 18, y = e.clientY + 14, w = 344, h = pv.offsetHeight || 480; if (x + w > window.innerWidth) x = e.clientX - w - 18; if (y + h > window.innerHeight) y = Math.max(4, window.innerHeight - h - 4); pv.style.left = x + 'px'; pv.style.top = y + 'px'; }
  document.addEventListener('mouseover', function (e) {
    var a = e.target.closest ? e.target.closest('a[href^="/review/"]') : null; if (!a) return;
    var m = a.getAttribute('href').match(/^\/review\/(\d+)/); if (!m) return;
    pvId = m[1]; clearTimeout(pvTimer); pvMove(e);
    pvTimer = setTimeout(function () { var im = pv.querySelector('img'); im.src = '/preview/' + pvId + '.jpg'; im.onload = function () { if (pvId) pv.style.display = 'block'; }; }, 280);
  });
  document.addEventListener('mousemove', function (e) { if (pvId) pvMove(e); });
  document.addEventListener('mouseout', function (e) { var a = e.target.closest ? e.target.closest('a[href^="/review/"]') : null; if (!a) return; pvId = null; clearTimeout(pvTimer); pv.style.display = 'none'; });
  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey || /^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(e.target.tagName)) return;
    var a = document.querySelector(e.key === 'ArrowLeft' ? 'a[rel=prev]' : e.key === 'ArrowRight' ? 'a[rel=next]' : '');
    if (a) location.href = a.href;
  });
})();
