/* SAShiny view toggle for paired outputs (spec CONTRACT.md section 8.6).
 *
 * A paired card holds two panes, the original SAS graph ("sas") and the
 * SAShiny chart ("sashiny"). Switching happens in the browser only. The choice
 * is kept in sessionStorage so a card re-rendered after a new run keeps it.
 * This file is shared verbatim by the R package and the Python library.
 */
(function () {
  "use strict";
  if (window.SAShinyToggle) {
    return;
  }
  var memory = {};
  var VIEWS = ["sas", "sashiny"];

  function load(key) {
    try {
      return window.sessionStorage.getItem(key);
    } catch (e) {
      return Object.prototype.hasOwnProperty.call(memory, key) ? memory[key] : null;
    }
  }

  function save(key, value) {
    try {
      if (value === null) {
        window.sessionStorage.removeItem(key);
      } else {
        window.sessionStorage.setItem(key, value);
      }
    } catch (e) {
      if (value === null) {
        delete memory[key];
      } else {
        memory[key] = value;
      }
    }
  }

  function groupKey(group) {
    return "sashiny-view:" + group;
  }

  function cardKey(card) {
    return groupKey(card.getAttribute("data-sashiny-group")) + ":" +
      card.getAttribute("data-sashiny-output");
  }

  function valid(view) {
    return VIEWS.indexOf(view) >= 0 ? view : null;
  }

  function each(list, fn) {
    for (var i = 0; i < list.length; i++) {
      fn(list[i]);
    }
  }

  function pressButtons(scope, selector, view) {
    each(scope.querySelectorAll(selector), function (button) {
      var on = button.getAttribute("data-sashiny-set") === view;
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.classList.toggle("active", on);
    });
  }

  function showCard(card, view) {
    card.setAttribute("data-sashiny-view", view);
    each(card.querySelectorAll("[data-sashiny-pane]"), function (pane) {
      pane.hidden = pane.getAttribute("data-sashiny-pane") !== view;
    });
    pressButtons(card, "[data-sashiny-card-toggle] [data-sashiny-set]", view);
    if (view === "sashiny") {
      // Interactive charts drawn while hidden need to measure their pane again.
      window.setTimeout(function () {
        window.dispatchEvent(new Event("resize"));
      }, 0);
    }
  }

  function initCard(card) {
    var view = valid(load(cardKey(card))) ||
      valid(load(groupKey(card.getAttribute("data-sashiny-group")))) ||
      valid(card.getAttribute("data-sashiny-default")) || "sashiny";
    showCard(card, view);
  }

  function byGroup(selector, group) {
    var out = [];
    each(document.querySelectorAll(selector), function (node) {
      if (node.getAttribute("data-sashiny-group") === group) {
        out.push(node);
      }
    });
    return out;
  }

  function cardsOf(group) {
    return byGroup("[data-sashiny-paired]", group);
  }

  // The module toggle shows a view as pressed only when every card shows it.
  function syncGroup(group) {
    var cards = cardsOf(group);
    var view = null;
    if (cards.length === 0) {
      view = valid(load(groupKey(group)));
    } else {
      view = cards[0].getAttribute("data-sashiny-view");
      each(cards, function (card) {
        if (card.getAttribute("data-sashiny-view") !== view) {
          view = null;
        }
      });
    }
    each(byGroup("[data-sashiny-group-toggle]", group), function (toggle) {
      var shown = view;
      if (cards.length === 0 && !shown) {
        shown = valid(toggle.getAttribute("data-sashiny-default"));
      }
      pressButtons(toggle, "[data-sashiny-set]", shown);
    });
  }

  function scan(root) {
    if (!root || root.nodeType !== 1) {
      return;
    }
    var groups = {};
    var nodes = [];
    if (root.matches && root.matches("[data-sashiny-paired], [data-sashiny-group-toggle]")) {
      nodes.push(root);
    }
    each(root.querySelectorAll("[data-sashiny-paired], [data-sashiny-group-toggle]"),
      function (node) {
        nodes.push(node);
      });
    each(nodes, function (node) {
      if (node.hasAttribute("data-sashiny-paired")) {
        initCard(node);
      }
      groups[node.getAttribute("data-sashiny-group")] = true;
    });
    for (var group in groups) {
      if (Object.prototype.hasOwnProperty.call(groups, group)) {
        syncGroup(group);
      }
    }
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest ? event.target.closest("[data-sashiny-set]") : null;
    if (!button) {
      return;
    }
    var view = valid(button.getAttribute("data-sashiny-set"));
    if (!view) {
      return;
    }
    var toggle = button.closest("[data-sashiny-group-toggle]");
    if (toggle) {
      var group = toggle.getAttribute("data-sashiny-group");
      save(groupKey(group), view);
      each(cardsOf(group), function (card) {
        save(cardKey(card), null);
        showCard(card, view);
      });
      syncGroup(group);
      return;
    }
    var card = button.closest("[data-sashiny-paired]");
    if (card) {
      save(cardKey(card), view);
      showCard(card, view);
      syncGroup(card.getAttribute("data-sashiny-group"));
    }
  });

  if (window.MutationObserver) {
    new MutationObserver(function (records) {
      each(records, function (record) {
        each(record.addedNodes, scan);
      });
    }).observe(document.documentElement, {childList: true, subtree: true});
  }

  function start() {
    scan(document.body);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }

  window.SAShinyToggle = {scan: scan};
})();
