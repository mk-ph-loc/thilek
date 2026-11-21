/* TH-ILEK διεπαφή 0.18: tooltips σε κάθε κουμπί/πεδίο, χρώματα ρόλων πεδίων, σταθερό μενού, εργαλειοθήκες. Χωρίς εξωτερικές βιβλιοθήκες. */
(function () {
  'use strict';
  var d = document;
  function ready(f) { if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', f); else f(); }
  function norm(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
  function strip(s) { return norm(s).replace(/^[^A-Za-zΑ-Ωα-ωά-ώ0-9]+/, '').replace(/\s*\(Ctrl\+S\)/, ''); }

  /* ---- λεξικό βοήθειας (κείμενο κουμπιού ή name=value) ---- */
  var TIPS = {
    'Φίλτρο': 'Εφαρμόζει τα φίλτρα της φόρμας στη λίστα.', 'Εφαρμογή φίλτρων': 'Εφαρμόζει όλα τα φίλτρα και ξαναφορτώνει τη λίστα.', 'Καθαρισμός': 'Καθαρίζει όλα τα πεδία φίλτρων.',
    'Αναζήτηση': 'Ψάχνει στο βιβλίο και στα ερωτήματα. Με εισαγωγικά ψάχνεις ακριβή φράση.', 'Δημιουργία': 'Δημιουργεί νέο στοιχείο με το όνομα που έγραψες.', 'Αποθήκευση': 'Αποθηκεύει τις αλλαγές. Δεν αναιρείται αυτόματα.',
    'Εισαγωγή': 'Εισάγει το αρχείο που διάλεξες ως νέο έγγραφο.', 'Μετονομασία': 'Αλλάζει το όνομα του στοιχείου.', 'Διαγραφή': 'Διαγράφει το στοιχείο. Δες την προειδοποίηση πριν επιβεβαιώσεις.',
    'διαγραφή': 'Διαγράφει το στοιχείο.', 'αφαίρεση': 'Αφαιρεί το στοιχείο από τη λίστα (δεν σβήνει τα δεδομένα της τράπεζας).', 'επιβεβαίωση': 'Επιβεβαιώνει τη σύνδεση ως σωστή (μένει και μετά το rebuild).',
    'Ορισμός': 'Ορίζει την υποενότητα που διάλεξες ως σύνδεση του ερωτήματος.', 'μεταφορά': 'Μεταφέρει το ερώτημα στο θέμα που διάλεξες.', 'Προσθήκη': 'Προσθέτει την ετικέτα στα επιλεγμένα.', 'Αφαίρεση': 'Αφαιρεί την ετικέτα από τα επιλεγμένα.',
    '+': 'Προσθέτει την ετικέτα στα επιλεγμένα.', '−': 'Αφαιρεί την ετικέτα που έγραψες από τα επιλεγμένα.', '↑': 'Μετακίνηση προς τα πάνω.', '↓': 'Μετακίνηση προς τα κάτω.',
    'Προσθήκη σε διαγώνισμα': 'Βάζει τα επιλεγμένα ερωτήματα σε διαγώνισμα.', 'Δημιουργία στοιχείων quiz': 'Φτιάχνει στοιχεία quiz από τα επιλεγμένα ερωτήματα.', 'Αποθήκευση επιλογής + κριτηρίων': 'Αποθηκεύει την επιλογή ως συλλογή μαζί με τα φίλτρα που την έβγαλαν.',
    'Προβολή/εκτύπωση': 'Ανοίγει σύνθετο έγγραφο έτοιμο για εκτύπωση σε νέα καρτέλα.', 'Συγχώνευση': 'Συγχωνεύει τα επιλεγμένα θέματα σε ένα PDF.', 'Μετατροπή σε Markdown': 'Δημιουργεί έγγραφο Markdown στα Έγγραφα MD.',
    'Μετατροπή σε Markdown έγγραφο': 'Δημιουργεί έγγραφο Markdown από τα επιλεγμένα.', 'Reveal.js': 'Παρουσίαση Reveal.js από τις λύσεις, με τη σειρά και το στυλ που διάλεξες.', 'HTML μαθητή': 'Αυτόνομη σελίδα για μαθητές με κρυφές λύσεις και quiz.',
    'Markdown/Word': 'Έγγραφο Markdown (και Word) με τις ενότητες που διάλεξες.', 'Moodle XML': 'Αρχείο Moodle XML από τα quiz των λύσεων (δεν έχει δοκιμαστεί σε πραγματικό Moodle).',
    'Λήψη PDF': 'Κατεβάζει το PDF στον υπολογιστή.', 'Προβολή PDF (νέα καρτέλα)': 'Ανοίγει το PDF σε νέα καρτέλα.', 'Δημιουργία PDF': 'Φτιάχνει το PDF με τις ρυθμίσεις.', 'Δημιουργία HTML': 'Φτιάχνει το αυτόνομο HTML.',
    'Προεπισκόπηση →': 'Δείχνει τη σειρά των ερωτημάτων πριν φτιαχτεί το PDF.', 'Περιήγηση ένα-ένα →': 'Ανοίγει το πρώτο ερώτημα των φίλτρων και προχωράς με ←/→.', 'Σάρωση φακέλου': 'Διαβάζει ξανά τα αρχεία λύσεων .md (χωρίς rebuild).',
    'Χτίσιμο ευρετηρίου τώρα': 'Χτίζει το ευρετήριο αναζήτησης (λίγα δευτερόλεπτα).', 'Ανανέωση ευρετηρίου': 'Ξαναχτίζει το ευρετήριο αναζήτησης μετά από αλλαγή στα PDF.', 'Αποθήκευση (Ctrl+S)': 'Αποθηκεύει το έγγραφο.',
    'Αποθήκευση (✔ έλεγξα)': 'Αποθηκεύει τις συνδέσεις του ερωτήματος και τις σημειώνει ως ελεγμένες.', 'Προσθήκη των επιλεγμένων στο quiz': 'Προσθέτει τα επιλεγμένα ερωτήματα στο quiz.', 'Προσθήκη τυχαίων': 'Προσθέτει τυχαία ερωτήματα με τα κριτήρια που όρισες.',
    'Έλεγχος απαντήσεων': 'Ελέγχει όλες τις απαντήσεις και δείχνει βαθμολογία.', 'Έλεγχος': 'Ελέγχει την απάντησή σου.', 'Δείξε την απάντηση': 'Εμφανίζει τη σωστή απάντηση.', 'Ανακάτεμα': 'Ανακατεύει τη σειρά των ερωτήσεων.',
    'Εμφάνιση': 'Εφαρμόζει την επιλογή εμφάνισης.', 'Αλλαγή σελίδας': 'Βάζει αλλαγή σελίδας για το Word (\\newpage).', 'Τίτλος': 'Μετατρέπει τη γραμμή σε τίτλο.', 'Λίστα': 'Ξεκινά λίστα με κουκκίδες.', 'Παράθεση': 'Μετατρέπει τη γραμμή σε παράθεση.',
    '+ εικόνα ερωτήματος': 'Βάζει στο έγγραφο την εικόνα του ερωτήματος με τον αριθμό που έγραψες.', '+ εικόνα λύσης': 'Βάζει την εικόνα λύσης του ερωτήματος.', 'Αποθήκευση εγγράφου ως αρχείο στον server (07_EXAGOGES)': 'Γράφει το έγγραφο ως αρχείο στον φάκελο 07_EXAGOGES.',
    '↻ Ξανατρέξιμο κριτηρίων (αντικαθιστά τα μέλη)': 'Ξανατρέχει τα κριτήρια και αντικαθιστά τα μέλη της συλλογής.', 'Ανάκτηση': 'Επαναφορά.', 'Upload': 'Ανεβάζει τα αρχεία στον τρέχοντα φάκελο, μετά από έλεγχο.',
    'Όλα': 'Επιλέγει όλα τα στοιχεία της λίστας.', 'Κανένα': 'Αφαιρεί κάθε επιλογή.', 'Λήψη zip': 'Κατεβάζει τα επιλεγμένα ως zip.', 'Στον κάδο': 'Μεταφέρει τα επιλεγμένα στον κάδο (αναιρείται από τον Κάδο).', 'Επαναφορά': 'Επαναφέρει τα επιλεγμένα στην αρχική τους θέση.'
  };
  var ACT = { exam: 'Βάζει τα επιλεγμένα ερωτήματα σε διαγώνισμα.', quiz: 'Φτιάχνει στοιχεία quiz.', tag: 'Προσθέτει την ετικέτα που έγραψες.', untag: 'Αφαιρεί την ετικέτα που έγραψες.', md: 'Δημιουργεί έγγραφο Markdown.', doc: 'Ανοίγει έγγραφο για εκτύπωση.', merge: 'Συγχώνευση σε PDF.', save: 'Αποθηκεύει ως συλλογή.', reveal: 'Παρουσίαση Reveal.js.', html: 'HTML για μαθητές.', solmd: 'Markdown/Word.', moodle: 'Moodle XML.' };
  var HDR = { 'Αναζήτηση': 'Αναζήτηση πλήρους κειμένου σε βιβλίο και ερωτήματα.', 'Θέματα': 'Λίστα θεμάτων ΙΕΠ και έλεγχος συνδέσεων.', 'Ερωτήματα': 'Πίνακας ερωτημάτων με φίλτρα και ενέργειες.', '★ Αγαπημένα': 'Μόνο τα ερωτήματα με αστέρι.', 'Ύλη/σελίδα': 'Τι καλύπτεται μέχρι μια σελίδα του βιβλίου.',
    'Ετικέτες': 'Μαζική διαχείριση ετικετών.', 'Αποθηκευμένα': 'Διαγωνίσματα, quiz, συλλογές.', 'Συγχώνευση PDF': 'Συγχώνευση θεμάτων ή ερωτημάτων σε PDF.', 'Εξαγωγή HTML': 'Αυτόνομο HTML από θέματα.', 'Διαγωνίσματα': 'Παραγωγή διαγωνισμάτων.', 'Quiz': 'Quiz και εξαγωγές.',
    'Λύσεις': 'Λύσεις εκπαιδευτικού, Reveal, HTML μαθητή, Moodle.', 'Έγγραφα MD': 'Έγγραφα Markdown/Word.', 'Αρχεία': 'File browser: αρχεία του server.', 'Οδηγίες': 'Εγχειρίδιο χρήσης.', 'Ρυθμίσεις': 'Ρυθμίσεις: διαγράμματα (SVG ή Mermaid) και βοήθεια σελίδας.', 'Ερωτήσεις-απαντήσεις': 'Εγχειρίδιο βοήθειας με ερωτήσεις και απαντήσεις και αναζήτηση.', 'Αποθήκευση ρυθμίσεων': 'Γράφει τις ρυθμίσεις στη βάση.' };

  function tipFor(el) {
    var t = el.getAttribute('data-tip') || el.getAttribute('title'); if (t) return t;
    var tag = el.tagName, type = (el.type || '').toLowerCase(), txt = norm(el.textContent || el.value), key = strip(txt);
    if (tag === 'A' && el.closest('header')) return HDR[txt] || HDR[key] || ('Μετάβαση: ' + txt);
    if (tag === 'BUTTON' || (tag === 'INPUT' && (type === 'submit' || type === 'button')) || (tag === 'A' && el.classList.contains('btn'))) {
      if (el.name === 'act' && ACT[el.value] && !TIPS[txt]) return ACT[el.value];
      if (el.name === 'action' && el.value) { var v = el.value.split(':')[0]; return TIPS[txt] || TIPS[key] || ({ up: 'Μετακίνηση πάνω.', down: 'Μετακίνηση κάτω.', delete: 'Διαγραφή.', remove: 'Αφαίρεση.', add: 'Προσθήκη.', confirm: 'Επιβεβαίωση.', save: 'Αποθήκευση.', group: 'Μεταφορά.' }[v]) || ('Ενέργεια: ' + txt); }
      return TIPS[txt] || TIPS[key] || ('Ενέργεια: ' + (txt || el.name || 'κουμπί') + '.');
    }
    if (tag === 'SUMMARY') return 'Κλικ για εμφάνιση ή απόκρυψη.';
    var lab = el.closest('label'), ln = lab ? strip(lab.textContent) : (el.getAttribute('placeholder') || el.name || '');
    if (type === 'checkbox') return el.classList.contains('r-sel') ? 'Επιλογή γραμμής: οι ενέργειες της μπάρας εφαρμόζονται στις τσεκαρισμένες.' : 'Ρύθμιση ναι/όχι: ' + ln + '.';
    if (type === 'radio') return 'Επιλογή ενός από πολλά: ' + ln + '.';
    if (tag === 'SELECT') return 'Λίστα επιλογής: ' + (ln || 'διάλεξε τιμή') + '.';
    if (type === 'file') return 'Επιλογή αρχείου από τον υπολογιστή σου.';
    if (tag === 'TEXTAREA') return 'Πεδίο κειμένου: ' + ln + '.';
    if (tag === 'INPUT') return 'Πεδίο εισαγωγής: ' + ln + '.';
    return '';
  }

  /* ---- ρόλοι πεδίων και χρώματα ---- */
  var SELNAMES = /^(sel|ids|qids|keys|dids|items|pick|q|sid|did|exam|quiz|rows|docs)$/i;
  function roles() {
    d.querySelectorAll('input,select,textarea,button,.btn').forEach(function (el) {
      var t = (el.type || '').toLowerCase(), tag = el.tagName;
      if (tag === 'INPUT' && t === 'checkbox') el.classList.add(el.classList.contains('selbox') || SELNAMES.test(el.name) || el.hasAttribute('data-all') || el.closest('td') ? 'r-sel' : 'r-opt');
      else if (tag === 'INPUT' && t === 'radio') el.classList.add('r-opt');
      else if (tag === 'SELECT' && el.id !== 'theme') el.classList.add('r-list');
      else if (tag === 'TEXTAREA' || (tag === 'INPUT' && (t === 'text' || t === 'number' || t === 'search' || t === '' || t === 'password' || t === 'date'))) el.classList.add('r-txt');
      else if (tag === 'INPUT' && t === 'file') el.classList.add('r-file');
      else if ((tag === 'BUTTON' || el.classList.contains('btn')) && /διαγραφ|αφαίρεση|κάδο|✖|οριστικ|ΔΙΑΓΡΑΦΗ|Επαναφορά προεπιλογών/i.test(el.textContent + ' ' + el.value) && !/Επαναφορά$/.test(norm(el.textContent))) el.classList.add('danger');
    });
    d.querySelectorAll('tr').forEach(function (tr) {
      var b = tr.querySelector('input.r-sel'); if (!b) return;
      function s() { tr.classList.toggle('sel-on', b.checked); } b.addEventListener('change', s); s();
    });
  }

  /* ---- tooltips ---- */
  var OFF = (d.documentElement.getAttribute('data-notips') || '').split(',').filter(Boolean);    // είδη χωρίς tooltip (Ρυθμίσεις)
  function kindOf(el) {
    var tag = el.tagName, t = (el.type || '').toLowerCase(), c = el.classList;
    if (tag === 'A' && el.closest('header')) return 'hdr';
    if (tag === 'SUMMARY') return 'sum';
    if (c.contains('danger')) return 'danger';
    if (c.contains('r-sel')) return 'sel'; if (c.contains('r-opt')) return 'opt'; if (c.contains('r-list')) return 'list'; if (c.contains('r-txt')) return 'txt'; if (c.contains('r-file')) return 'file';
    if (tag === 'BUTTON' || c.contains('btn') || t === 'submit' || t === 'button') return 'btn';
    return '';
  }
  function tooltips() {
    if (OFF.length) d.querySelectorAll('[title]').forEach(function (el) { if (OFF.indexOf(kindOf(el)) >= 0) { el.setAttribute('data-tip', el.getAttribute('title')); el.removeAttribute('title'); } });
    var tip = d.createElement('div'); tip.id = 'tip'; d.body.appendChild(tip); var cur = null;
    function show(el, x, y) {
      if (OFF.indexOf(kindOf(el)) >= 0) { tip.style.display = 'none'; return; }
      var t = tipFor(el); if (!t) return; if (el.hasAttribute('title')) { el.setAttribute('data-tip', el.getAttribute('title')); el.removeAttribute('title'); }
      tip.textContent = t; tip.style.display = 'block'; move(x, y);
    }
    function move(x, y) { var w = tip.offsetWidth, h = tip.offsetHeight, X = Math.min(x + 14, innerWidth - w - 8), Y = y + 18; if (Y + h > innerHeight - 8) Y = y - h - 10; tip.style.left = Math.max(4, X) + 'px'; tip.style.top = Math.max(4, Y) + 'px'; }
    var SEL = 'button,input,select,textarea,summary,header a,a.btn,.star,[data-tip],[title],label.f.chk';
    d.addEventListener('mouseover', function (e) { var el = e.target.closest && e.target.closest(SEL); if (!el || el === cur) return; if (el.tagName === 'LABEL') { var i = el.querySelector('input,select'); if (i) el = i; } cur = el; show(el, e.clientX, e.clientY); });
    d.addEventListener('mousemove', function (e) { if (cur) move(e.clientX, e.clientY); });
    d.addEventListener('mouseout', function (e) { if (cur && !cur.contains(e.relatedTarget)) { cur = null; tip.style.display = 'none'; } });
    d.addEventListener('mousedown', function () { tip.style.display = 'none'; });
    d.addEventListener('focusin', function (e) { var el = e.target; if (el.matches && el.matches(SEL)) { var r = el.getBoundingClientRect(); show(el, r.left, r.bottom - 14); } });
    d.addEventListener('focusout', function () { tip.style.display = 'none'; });
    d.querySelectorAll('button,input[type=submit],a.btn').forEach(function (b) { if (!b.getAttribute('title') && !b.getAttribute('data-tip')) b.setAttribute('data-tip', tipFor(b)); });    // κάθε κουμπί έχει tooltip (και στο εγγενές hover)
  }

  /* ---- επιλογή όλων/κανενός + μετρητής ---- */
  function boxes(name) { return [].slice.call(d.querySelectorAll('input[type=checkbox][name="' + name + '"]')); }
  function count() { var c = d.getElementById('count'); if (!c || d.querySelector('input[data-all]')) return; c.textContent = d.querySelectorAll('input.r-sel:checked:not([data-all])').length; }
  function selection() {
    d.addEventListener('click', function (e) {
      var b = e.target.closest('[data-selall],[data-selnone]'); if (!b) return; e.preventDefault();
      var n = b.getAttribute('data-selall') || b.getAttribute('data-selnone'), on = b.hasAttribute('data-selall');
      boxes(n).forEach(function (x) { x.checked = on; x.dispatchEvent(new Event('change', { bubbles: true })); }); count();
    });
    d.addEventListener('change', function (e) { if (e.target.classList && e.target.classList.contains('r-sel')) count(); });
    count();
  }

  /* ---- λίστες με ↑↓ ---- */
  function reorder() {
    d.addEventListener('click', function (e) {
      var b = e.target.closest('ul.reorder button'); if (!b) return; e.preventDefault(); var li = b.closest('li'), ul = li.parentNode;
      if (b.classList.contains('up') && li.previousElementSibling) ul.insertBefore(li, li.previousElementSibling);
      if (b.classList.contains('dn') && li.nextElementSibling) ul.insertBefore(li.nextElementSibling, li);
    });
  }

  /* ---- σταθερό μενού: ύψος για τα sticky στοιχεία ---- */
  function header() { var h = d.querySelector('header'); function s() { if (h) d.documentElement.style.setProperty('--hh', h.offsetHeight + 'px'); } s(); addEventListener('resize', s); }

  /* ---- ενέργειες JS για τις εργαλειοθήκες ---- */
  var JSACT = {
    selall: function () { d.querySelectorAll('input.r-sel').forEach(function (x) { x.checked = true; x.dispatchEvent(new Event('change', { bubbles: true })); }); count(); },
    selnone: function () { d.querySelectorAll('input.r-sel').forEach(function (x) { x.checked = false; x.dispatchEvent(new Event('change', { bubbles: true })); }); count(); },
    invert: function () { d.querySelectorAll('input.r-sel').forEach(function (x) { x.checked = !x.checked; x.dispatchEvent(new Event('change', { bubbles: true })); }); count(); },
    top: function () { scrollTo({ top: 0, behavior: 'smooth' }); }, bottom: function () { scrollTo({ top: d.body.scrollHeight, behavior: 'smooth' }); },
    print: function () { print(); }, reload: function () { location.reload(); }
  };

  /* ---- πλωτή εργαλειοθήκη ---- */
  function toolbox() {
    if (d.getElementById('tbfab') || !window.fetch) return;
    var KEY = 'thilek_tb', st = {}; try { st = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) {}
    function save() { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (e) {} }
    fetch('/toolbox/api', { credentials: 'same-origin' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j) return; var bs = j.boxes.filter(function (b) { return b.enabled; }); if (!bs.length) return;
      var fab = d.createElement('button'); fab.id = 'tbfab'; fab.type = 'button'; fab.textContent = '🧰'; fab.setAttribute('data-tip', 'Εργαλειοθήκη: γρήγορες ενέργειες. Ρυθμίζεται από «Ρύθμιση εργαλειοθηκών».');
      var box = d.createElement('div'); box.id = 'tbox';
      box.innerHTML = '<div class=tbh><b>🧰 Εργαλειοθήκη</b><span><a href="/toolbox" style="color:#fff" data-tip="Ρύθμιση: τι περιέχει κάθε εργαλειοθήκη">⚙</a> <a href="#" id=tbx style="color:#fff;text-decoration:none" data-tip="Κλείσιμο">✕</a></span></div><div class=tbt></div><div class=tbi></div><div class=tbf></div>';
      d.body.appendChild(box); d.body.appendChild(fab); var tabs = box.querySelector('.tbt'), items = box.querySelector('.tbi'), cur = Math.min(st.tab || 0, bs.length - 1);
      function render() {
        tabs.innerHTML = ''; bs.forEach(function (b, i) { var t = d.createElement('button'); t.type = 'button'; t.textContent = b.name; t.className = i === cur ? 'on' : ''; t.setAttribute('data-tip', 'Εργαλειοθήκη ' + b.slot + ': ' + b.name); t.onclick = function () { cur = i; st.tab = i; save(); render(); }; tabs.appendChild(t); });
        items.innerHTML = ''; bs[cur].items.forEach(function (k) {
          var c = j.catalog[k]; if (!c) return; var el;
          if (c.go.indexOf('js:') === 0) { el = d.createElement('button'); el.type = 'button'; el.onclick = function () { var f = JSACT[c.go.slice(3)]; if (f) f(); }; }
          else { el = d.createElement('a'); el.href = c.go; }
          el.textContent = c.icon + ' ' + c.label; el.setAttribute('data-tip', c.tip); items.appendChild(el);
        });
        if (!bs[cur].items.length) items.innerHTML = '<small>Άδεια. Πρόσθεσε ενέργειες από το ⚙.</small>';
      }
      function open(v) { box.style.display = v ? 'block' : 'none'; st.open = v; save(); if (v) render(); }
      fab.onclick = function () { open(box.style.display !== 'block'); }; box.querySelector('#tbx').onclick = function (e) { e.preventDefault(); open(false); };
      if (st.x != null) { box.style.left = st.x + 'px'; box.style.top = st.y + 'px'; box.style.right = 'auto'; box.style.bottom = 'auto'; }
      var h = box.querySelector('.tbh'), drag = null;
      h.addEventListener('mousedown', function (e) { if (e.target.closest('a')) return; var r = box.getBoundingClientRect(); drag = [e.clientX - r.left, e.clientY - r.top]; e.preventDefault(); });
      d.addEventListener('mousemove', function (e) { if (!drag) return; var x = Math.max(0, Math.min(innerWidth - 60, e.clientX - drag[0])), y = Math.max(0, Math.min(innerHeight - 40, e.clientY - drag[1])); box.style.left = x + 'px'; box.style.top = y + 'px'; box.style.right = 'auto'; box.style.bottom = 'auto'; st.x = x; st.y = y; });
      d.addEventListener('mouseup', function () { if (drag) { drag = null; save(); } });
      if (st.open) open(true);
    }).catch(function () {});
  }

  ready(function () { roles(); tooltips(); selection(); reorder(); header(); toolbox(); });
})();
