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

  function closeModal() {
    var modal = document.getElementById('modal-container');
    if (modal) modal.innerHTML = '';
  }

  document.addEventListener('click', function (event) {
    document.querySelectorAll('details[data-dropdown][open]').forEach(function (d) {
      if (!d.contains(event.target)) {
        d.removeAttribute('open');
      }
    });
    if (event.target.closest('[data-modal-close]') || (event.target.matches && event.target.matches('[data-modal-backdrop]'))) {
      closeModal();
      return;
    }
    var copy = event.target.closest('[data-copy]');
    if (copy) {
      navigator.clipboard.writeText(copy.dataset.copy);
      return;
    }
    var chip = event.target.closest('[data-filter]');
    if (chip) clearFilter(chip.dataset.filter, chip.dataset.value || '');
    var tabBtn = event.target.closest('[data-surveillance-tab]');
    if (tabBtn) {
      var targetTab = tabBtn.dataset.surveillanceTab;
      var container = document.getElementById('surveillance-body');
      if (container) {
        container.querySelectorAll('[data-surveillance-tab]').forEach(function (btn) {
          if (btn === tabBtn) {
            btn.classList.add('bg-emerald-600', 'text-white');
            btn.classList.remove('bg-slate-800/80', 'text-slate-300');
          } else {
            btn.classList.remove('bg-emerald-600', 'text-white');
            btn.classList.add('bg-slate-800/80', 'text-slate-300');
          }
        });
        container.querySelectorAll('[data-surveillance-item]').forEach(function (el) {
          var itemType = el.dataset.surveillanceItem;
          if (targetTab === 'all') {
            el.style.display = itemType === 'history' ? 'none' : '';
          } else if (targetTab === 'history') {
            el.style.display = itemType === 'history' ? '' : 'none';
          } else {
            el.style.display = itemType === targetTab ? '' : 'none';
          }
        });
      }
      return;
    }
  });

  // Settings tabs: show one panel, remember it in the URL hash (#trackers...).
  function showSettingsTab(key) {
    var panels = document.querySelectorAll('[data-settings-panel]');
    if (!panels.length) return;
    var exists = Array.prototype.some.call(panels, function (p) { return p.dataset.settingsPanel === key; });
    if (!exists) key = panels[0].dataset.settingsPanel;
    panels.forEach(function (p) { p.classList.toggle('hidden', p.dataset.settingsPanel !== key); });
    document.querySelectorAll('[data-settings-tab]').forEach(function (btn) {
      var active = btn.dataset.settingsTab === key;
      btn.classList.toggle('bg-emerald-600', active);
      btn.classList.toggle('text-white', active);
      btn.classList.toggle('bg-slate-800/80', !active);
      btn.classList.toggle('text-slate-300', !active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
      if (active && btn.scrollIntoView) btn.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    });
  }

  document.addEventListener('click', function (event) {
    var settingsTab = event.target.closest('[data-settings-tab]');
    if (!settingsTab) return;
    var key = settingsTab.dataset.settingsTab;
    history.replaceState(null, '', '#' + key);
    showSettingsTab(key);
  });

  function showTabFromHash() {
    showSettingsTab(location.hash.replace('#', ''));
  }
  document.addEventListener('DOMContentLoaded', showTabFromHash);
  window.addEventListener('hashchange', showTabFromHash);

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closeModal();
  });

  // Broken poster -> drop the <img> so the placeholder icon shows. Error events don't
  // bubble, hence the capture phase.
  document.addEventListener('error', function (event) {
    var el = event.target;
    if (el instanceof HTMLImageElement && el.hasAttribute('data-poster')) el.remove();
  }, true);
})();
