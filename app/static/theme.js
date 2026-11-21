// Επιλογή εμφάνισης: φορτώνεται στο <head> ώστε να μην αναβοσβήνει. Η επιλογή μένει στον browser.
(function () {
  var KEY = 'thilek_theme', ok = ['classic', 'dark', 'soft'];
  function get() { try { var v = localStorage.getItem(KEY); return ok.indexOf(v) >= 0 ? v : 'classic'; } catch (e) { return 'classic'; } }
  document.documentElement.setAttribute('data-theme', get());
  document.addEventListener('DOMContentLoaded', function () {
    var s = document.getElementById('theme'); if (!s) return;
    s.value = get();
    s.addEventListener('change', function () { try { localStorage.setItem(KEY, s.value); } catch (e) {} document.documentElement.setAttribute('data-theme', s.value); });
  });
})();
