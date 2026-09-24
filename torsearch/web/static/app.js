// TorrSearch front helpers, wired by event delegation from data-* attributes.
// Templates carry no inline JS: interpolated values can never run as code, and a
// strict Content-Security-Policy becomes possible later.
(function () {
  'use strict';

  // Reset one filter of the search form, then re-run the search.
  function clearFilter(name, value) {
    var form = document.getElementById('search-form');
    if (!form) return;
    if (name === 'quality' && value) {
      form.querySelectorAll('input[name="quality"]').forEach(function (cb) {
        if (cb.value === value) cb.checked = false;
      });
    } else if (name === 'min_seeders') {
      var seeders = form.querySelector('[name="min_seeders"]');
      if (seeders) seeders.value = '0';
    } else {
      var field = form.querySelector('[name="' + name + '"]');
      if (field) field.value = '';
    }
    htmx.trigger(form, 'submit');
  }

  document.addEventListener('click', function (event) {
    var copy = event.target.closest('[data-copy]');
    if (copy) {
      navigator.clipboard.writeText(copy.dataset.copy);
      return;
    }
    var chip = event.target.closest('[data-filter]');
    if (chip) clearFilter(chip.dataset.filter, chip.dataset.value || '');
  });

  // Broken poster -> drop the <img> so the placeholder icon shows. Error events don't
  // bubble, hence the capture phase.
  document.addEventListener('error', function (event) {
    var el = event.target;
    if (el instanceof HTMLImageElement && el.hasAttribute('data-poster')) el.remove();
  }, true);
})();
