// Προεπισκόπηση συγχώνευσης ερωτημάτων: αναδιάταξη (↑ ↓), αφαίρεση, αρίθμηση.
(function () {
  var ol = document.querySelector('.pqlist'); if (!ol) return;
  function renum() { var li = ol.querySelectorAll('.pq'); li.forEach(function (x, i) { x.querySelector('.pqn').textContent = (i + 1) + '.'; }); var c = document.getElementById('pqcount'); if (c) c.textContent = li.length; }
  ol.addEventListener('click', function (e) {
    var b = e.target.closest('button[data-act]'); if (!b) return; var li = b.closest('.pq'), a = b.dataset.act;
    if (a === 'up' && li.previousElementSibling) ol.insertBefore(li, li.previousElementSibling);
    else if (a === 'down' && li.nextElementSibling) ol.insertBefore(li.nextElementSibling, li);
    else if (a === 'del') li.remove();
    renum();
  });
  renum();
})();
