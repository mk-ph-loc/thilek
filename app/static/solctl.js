/* Επιλογή ενοτήτων και σειράς πριν την εξαγωγή λύσεων: βελάκια ↑↓ και έτοιμες διατάξεις. Η σειρά των <li> είναι η σειρά που στέλνει η φόρμα. */
(function () {
  function init(box) {
    if (box.dataset.ready) return; box.dataset.ready = '1';
    var ul = box.querySelector('.solord'), pre = box.querySelector('.solpre');
    ul.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return; var li = b.closest('li');
      if (b.classList.contains('up') && li.previousElementSibling) ul.insertBefore(li, li.previousElementSibling);
      if (b.classList.contains('dn') && li.nextElementSibling) ul.insertBefore(li.nextElementSibling, li);
    });
    pre.addEventListener('change', function () {
      if (!pre.value) return; var keys = pre.value.split(','), by = {}, i;
      [].forEach.call(ul.children, function (li) { by[li.dataset.k] = li; });
      var rest = [].slice.call(ul.children).filter(function (li) { return keys.indexOf(li.dataset.k) < 0; });
      for (i = 0; i < keys.length; i++) if (by[keys[i]]) { by[keys[i]].querySelector('input').checked = true; ul.appendChild(by[keys[i]]); }
      rest.forEach(function (li) { li.querySelector('input').checked = false; ul.appendChild(li); });
      pre.value = '';
    });
  }
  [].forEach.call(document.querySelectorAll('.solctl'), init);
})();
