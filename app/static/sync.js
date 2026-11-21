/* TH-ILEK 0.20.0: ζωντανή ενημέρωση της εργασίας /sync (χωρίς inline JS). */
(function () {
  var pre = document.getElementById('joblog'), st = document.getElementById('jobstate');
  if (!pre) return;
  var timer = null;
  function paint(j) {
    pre.textContent = j.log || '';
    pre.scrollTop = pre.scrollHeight;
    if (j.running) st.textContent = '⏳ τρέχει: ' + j.label;
    else if (j.rc === null || j.rc === undefined) st.textContent = '';
    else st.textContent = (j.rc === 0 ? '✔ τελείωσε' : '⚠ τελείωσε με κωδικό ' + j.rc) + ': ' + j.label;
  }
  function poll() {
    fetch(pre.dataset.url, { credentials: 'same-origin', cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
      paint(j);
      if (j.running) timer = setTimeout(poll, 2000);
      else { if (pre.dataset.busy === '1') location.reload(); }
    }).catch(function () { timer = setTimeout(poll, 5000); });
  }
  poll();
})();
