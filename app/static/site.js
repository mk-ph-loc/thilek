// Site builder (0.34): εργαλειοθήκη που εισάγει Markdown στη θέση του δρομέα και ζωντανή προεπισκόπηση της τρέχουσας σελίδας (POST χωρίς αποθήκευση).
(function () {
  var form = document.getElementById('stform'); if (!form) return;
  var ta = form.elements['body'], sid = form.getAttribute('data-sid'), pid = form.getAttribute('data-pid'), timer = null;
  var BLK = {
    callout_note: '::: callout note Σημείωση\n§\n:::', callout_tip: '::: callout tip Συμβουλή\n§\n:::', callout_warning: '::: callout warning Προσοχή\n§\n:::',
    math: ['$§$', 'inline'], mathblock: '$$\n§\n$$', bullets: '- §\n- \n- ', image: ['![§](/files/)', 'inline'], link: ['[§](https://)', 'inline'], pagelink: ['[§](thilek://page/)', 'inline'],
    code: '```python\n§\n```', cols: '::: cols\n§\n|||\n\n:::',
    quizyaml: '::: quiz\ntype: mcq\nstem: §\noptions:\n  - Α\n  - Β\n  - Γ\nanswer: 0\n:::', quizref: '::: quiz-ref §\n:::', deckref: '::: deck-ref §\n:::', file: '::: file §\n:::',
    embed: '::: embed §\nΛεζάντα\n:::', yt: '::: embed https://www.youtube.com/watch?v=§\nΛεζάντα\n:::', gg: '::: embed https://www.geogebra.org/m/§\nΛεζάντα\n:::',
    cj: '::: embed https://www.falstad.com/circuit/circuitjs.html§ ratio=4:3\nΚύκλωμα\n:::'
  };
  function preview() {
    var f = document.createElement('form'); f.method = 'post'; f.action = '/sites/' + sid + '/preview/' + pid; f.target = 'stprev'; f.style.display = 'none';
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.name === 'act') return;
      if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) return;
      var i = document.createElement('input'); i.type = 'hidden'; i.name = el.name; i.value = el.value; f.appendChild(i);
    });
    document.body.appendChild(f); f.submit(); document.body.removeChild(f);
  }
  function later() { clearTimeout(timer); timer = setTimeout(preview, 700); }
  function inDirective(text, pos) {                       // True αν ο δρομέας είναι μέσα σε οδηγία ::: (εκτός fenced code)
    var lines = text.slice(0, pos).split('\n'), fence = '', open = false;
    for (var i = 0; i < lines.length; i++) {
      var l = lines[i], m = /^ {0,3}(`{3,}|~{3,})/.exec(l);
      if (fence) { if (m && m[1].charAt(0) === fence.charAt(0) && m[1].length >= fence.length) fence = ''; continue; }
      if (m) { fence = m[1]; continue; }
      if (/^:::[ \t]+[A-Za-z]/.test(l)) open = true; else if (/^:::[ \t]*$/.test(l)) open = false;
    }
    return open;
  }
  function insert(snip, inline) {
    var v = ta.value, s = ta.selectionStart, e = ta.selectionEnd, sel = v.slice(s, e);
    if (!inline && snip.indexOf(':::') === 0 && inDirective(v, s)) {   // όχι εμφώλευση: μετά το κλείσιμο της τρέχουσας οδηγίας
      var re = /\n:::[ \t]*(?=\n|$)/g; re.lastIndex = s; var r = re.exec(v); s = e = r ? r.index + r[0].length : v.length; sel = '';
    }
    var before = v.slice(0, s), after = v.slice(e), pre = '', post = '';
    if (!inline) {
      pre = !before ? '' : (before.slice(-2) === '\n\n' ? '' : (before.slice(-1) === '\n' ? '\n' : '\n\n'));
      post = !after ? '\n' : (after.slice(0, 2) === '\n\n' ? '' : (after.charAt(0) === '\n' ? '\n' : '\n\n'));
    }
    var k = snip.indexOf('§'), text = snip.replace('§', sel);
    ta.value = before + pre + text + post + after; ta.focus();
    var c = (before + pre).length + k; ta.selectionStart = c; ta.selectionEnd = c + sel.length; later();
  }
  document.querySelectorAll('[data-blk]').forEach(function (b) {
    b.addEventListener('click', function () {
      var x = BLK[b.getAttribute('data-blk')]; if (!x) return;
      if (typeof x === 'string') insert(x, false); else insert(x[0], x[1] === 'inline');
    });
  });
  form.addEventListener('input', later); form.addEventListener('change', later);
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); var sv = form.querySelector('button[name=act][value=save]'); if (sv) sv.click(); }
  });
  preview();
})();
