function showToast(message) {
	var toast = document.getElementById("toast-notification");
	var toastMsg = document.getElementById("toast-message");
	if (!toast) return;
	if (toastMsg) toastMsg.innerText = message || "Copied to clipboard!";
	
	toast.classList.remove("hidden");
	toast.classList.add("show");
	
	setTimeout(function() {
		toast.classList.remove("show");
		setTimeout(function() {
			toast.classList.add("hidden");
		}, 300);
	}, 2500);
}

function copySmile(textToCopy, element) {
	copyGeneric(textToCopy, element, "SMILES string copied!");
}

function copyCompoundName(textToCopy, element) {
	copyGeneric(textToCopy, element, "Full compound name copied!");
}

function copyText(textToCopy, element, message) {
	copyGeneric(textToCopy, element, message || "Email address copied!");
}

function copyGeneric(textToCopy, element, message) {
	if (!textToCopy) return;

	if (navigator.clipboard && window.isSecureContext) {
		navigator.clipboard.writeText(textToCopy).then(function() {
			handleCopyFeedback(element, message);
		}).catch(function() {
			fallbackCopyText(textToCopy, element, message);
		});
	} else {
		fallbackCopyText(textToCopy, element, message);
	}
}

function fallbackCopyText(textToCopy, element, message) {
	let textArea = document.createElement("textarea");
	textArea.value = textToCopy;
	textArea.style.position = "fixed";
	textArea.style.left = "-999999px";
	textArea.style.top = "-999999px";
	document.body.appendChild(textArea);
	textArea.focus();
	textArea.select();

	try {
		document.execCommand('copy');
		handleCopyFeedback(element, message);
	} catch (err) {
		console.error('Fallback copy failed', err);
	}
	textArea.remove();
}

function handleCopyFeedback(element, message) {
	showToast(message || "Copied to clipboard!");
	if (element) {
		element.classList.add("copied-pulse");
		setTimeout(function() {
			element.classList.remove("copied-pulse");
		}, 800);
	}
}

function fillSearch(query) {
	var input = document.getElementById("compound-search-input");
	if (input) {
		input.value = query;
		var form = document.getElementById("search-form") || input.closest("form");
		if (form) {
			form.submit();
		}
	}
}

function submitResultsControls() {
	var form = document.getElementById("results-controls-form");
	if (form) {
		form.submit();
	}
}

function updateSortOrderUI() {
	var input = document.getElementById("sort-order-input");
	var arrow = document.getElementById("sort-order-arrow");
	var btn = document.getElementById("sort-order-btn");
	if (btn) {
		btn.disabled = !document.getElementById("sort-by-select") ||
			!document.getElementById("sort-by-select").value;
	}
	if (arrow && input) {
		arrow.textContent = input.value === "desc" ? "\u2193" : "\u2191";
	}
}

function onSortByChange() {
	var input = document.getElementById("sort-order-input");
	var select = document.getElementById("sort-by-select");
	if (input && select) {
		var val = select.value;
		if (val && val.startsWith("cluster_")) {
			input.value = "desc";
		} else {
			input.value = "asc";
		}
	}
	updateSortOrderUI();
	submitResultsControls();
}

function toggleSortOrder() {
	var input = document.getElementById("sort-order-input");
	var btn = document.getElementById("sort-order-btn");
	if (!input || (btn && btn.disabled)) return;
	input.value = input.value === "desc" ? "asc" : "desc";
	updateSortOrderUI();
	submitResultsControls();
}

function setResultsView(mode) {
	var matrixContainer = document.getElementById("matrix-container");
	var cardsContainer = document.getElementById("cards-container");
	var btnMatrix = document.getElementById("btn-matrix-view");
	var btnCards = document.getElementById("btn-cards-view");

	if (!matrixContainer || !cardsContainer) return;

	if (mode === 'cards') {
		matrixContainer.classList.add("hidden");
		cardsContainer.classList.remove("hidden");
		if (btnMatrix) btnMatrix.classList.remove("active");
		if (btnCards) btnCards.classList.add("active");
	} else {
		cardsContainer.classList.add("hidden");
		matrixContainer.classList.remove("hidden");
		if (btnCards) btnCards.classList.remove("active");
		if (btnMatrix) btnMatrix.classList.add("active");
	}
}

// ==========================================================================
// DESKTOP RESULTS LAYOUT (COLUMNS MATRIX / TRANSPOSED ROWS TABLE)
// ==========================================================================
var DESKTOP_LAYOUT_KEY = "cpcse_desktop_layout";

function setDesktopLayout(mode, persist) {
	var layout = (mode === "transposed") ? "transposed" : "matrix";
	var root = document.documentElement;

	root.classList.toggle("layout-transposed", layout === "transposed");
	root.classList.toggle("layout-matrix", layout === "matrix");

	var btnColumns = document.getElementById("btn-desktop-columns");
	var btnRows = document.getElementById("btn-desktop-rows");
	var isRows = layout === "transposed";

	if (btnColumns) {
		btnColumns.classList.toggle("active", !isRows);
		btnColumns.setAttribute("aria-pressed", String(!isRows));
	}
	if (btnRows) {
		btnRows.classList.toggle("active", isRows);
		btnRows.setAttribute("aria-pressed", String(isRows));
	}

	if (persist !== false) {
		try {
			localStorage.setItem(DESKTOP_LAYOUT_KEY, layout);
		} catch (e) {
			// Storage may be unavailable (private mode); the layout still works.
		}
	}
}

function initDesktopLayout() {
	var stored = null;
	try {
		stored = localStorage.getItem(DESKTOP_LAYOUT_KEY);
	} catch (e) {
		stored = null;
	}
	setDesktopLayout(stored === "transposed" ? "transposed" : "matrix", false);
}

// Input clear button listener and responsive initial view setup
document.addEventListener("DOMContentLoaded", function() {
	var searchInput = document.getElementById("compound-search-input");
	var clearBtn = document.getElementById("clear-btn");

	if (searchInput && clearBtn) {
		searchInput.addEventListener("input", function() {
			if (this.value.length > 0) {
				clearBtn.style.display = "block";
			} else {
				clearBtn.style.display = "none";
			}
		});

		clearBtn.addEventListener("click", function() {
			searchInput.value = "";
			clearBtn.style.display = "none";
			searchInput.focus();
		});
	}

	// On mobile devices (<= 768px), default results view to cards
	if (window.matchMedia && window.matchMedia("(max-width: 768px)").matches) {
		setResultsView("cards");
	}

	initDesktopLayout();
	initTagInput();
});

// ==========================================================================
// ADVANCED SEARCH INTERACTIVITY
// ==========================================================================

var substancesList = [];
var MAX_SEARCH_TERMS = 5;
var MIN_TERM_LENGTH = 3;

// Split raw keyword input on commas, whitespace, and newlines; drop empties.
function splitTermTokens(text) {
	return (text || "")
		.split(/[\s,]+/)
		.map(function(t) { return t.trim(); })
		.filter(function(t) { return t.length > 0; });
}

// Show a concise inline hint inside the advanced search panel.
function showAdvancedHint(message) {
	var hint = document.getElementById("adv-inline-hint");
	if (!hint) {
		showToast(message);
		return;
	}
	hint.innerText = message;
	hint.classList.remove("hidden");
}

function clearAdvancedHint() {
	var hint = document.getElementById("adv-inline-hint");
	if (hint) {
		hint.innerText = "";
		hint.classList.add("hidden");
	}
}

function toggleAdvancedSearch(forceState) {
	var panel = document.getElementById("adv-search-panel");
	var toggleBtn = document.getElementById("adv-search-toggle-btn");
	if (!panel) return;

	var isCurrentlyHidden = panel.classList.contains("hidden");
	var shouldShow = (typeof forceState === "boolean") ? forceState : isCurrentlyHidden;

	if (shouldShow) {
		panel.classList.remove("hidden");
		if (toggleBtn) {
			toggleBtn.classList.add("active");
			toggleBtn.setAttribute("aria-expanded", "true");
		}
		// Re-enable inputs for advanced search mode
		var hiddenSubstances = document.getElementById("substances-hidden");
		if (hiddenSubstances) hiddenSubstances.disabled = false;

		var skipCheck = document.getElementById("skip-svg-check");
		if (skipCheck) skipCheck.disabled = false;

		// Re-enable active threshold inputs
		var activeChecks = document.querySelectorAll(".cluster-filter-check[data-cluster]:checked");
		activeChecks.forEach(function(chk) {
			var key = chk.getAttribute("data-cluster");
			var input = document.getElementById("input-" + key);
			if (input) input.disabled = false;
		});

		// Re-enable the concentration range when its card is checked.
		var concCheck = document.getElementById("conc-filter-check");
		if (concCheck && concCheck.checked) {
			var concMin = document.getElementById("conc-min-input");
			var concMax = document.getElementById("conc-max-input");
			if (concMin) concMin.disabled = false;
			if (concMax) concMax.disabled = false;
		}

		// Allow submission without primary search input while in advanced mode
		var mainInputs = document.querySelectorAll("input[name='nm']");
		mainInputs.forEach(function(inp) { inp.removeAttribute("required"); });

		// Focus tag input if visible
		var tagInput = document.getElementById("tag-text-input");
		if (tagInput) tagInput.focus();
	} else {
		panel.classList.add("hidden");
		if (toggleBtn) {
			toggleBtn.classList.remove("active");
			toggleBtn.setAttribute("aria-expanded", "false");
		}
		var mainInputs = document.querySelectorAll("input[name='nm']");
		mainInputs.forEach(function(inp) { inp.setAttribute("required", "required"); });
	}
}

function focusTagInput() {
	var tagInput = document.getElementById("tag-text-input");
	if (tagInput) tagInput.focus();
}

function initTagInput() {
	var tagInput = document.getElementById("tag-text-input");
	var hiddenSubstances = document.getElementById("substances-hidden");

	// Preload existing substances from template if present
	if (hiddenSubstances && hiddenSubstances.value.trim().length > 0) {
		substancesList = splitTermTokens(hiddenSubstances.value)
			.filter(function(t) { return t.length >= MIN_TERM_LENGTH; })
			.slice(0, MAX_SEARCH_TERMS);
		renderTags();
	}

	if (tagInput) {
		tagInput.addEventListener("keydown", function(e) {
			if (e.key === "," || e.key === "Enter" || e.key === "Tab") {
				if (this.value.trim().length > 0) {
					e.preventDefault();
					addTag(this.value);
					this.value = "";
				}
			} else if (e.key === "Backspace" && this.value === "" && substancesList.length > 0) {
				removeTag(substancesList.length - 1);
			}
		});

		tagInput.addEventListener("blur", function() {
			flushPendingTagInput();
		});

		// Mobile keyboards often don't emit a keydown for "," — detect the
		// delimiter from the input value instead and tokenize immediately.
		tagInput.addEventListener("input", function() {
			if (this.value.indexOf(",") !== -1) {
				addTag(this.value);
				this.value = "";
			}
		});
	}

	// Before any search form submission, handle strict state isolation between Basic and Advanced search
	var searchForms = document.querySelectorAll("form[action='/search']");
	searchForms.forEach(function(form) {
		form.addEventListener("submit", function(e) {
			var advPanel = document.getElementById("adv-search-panel");
			var isAdvActive = advPanel && !advPanel.classList.contains("hidden");
			var mainInput = form.querySelector("input[name='nm']");

			if (isAdvActive) {
				// ADVANCED SEARCH MODE:
				flushPendingTagInput();

				// Normalize keyword list: enforce min length and the 5-term cap.
				var hadShortTerms = substancesList.some(function(t) { return t.length < MIN_TERM_LENGTH; });
				substancesList = substancesList
					.filter(function(t) { return t.length >= MIN_TERM_LENGTH; })
					.slice(0, MAX_SEARCH_TERMS);
				renderTags();
				syncSubstancesHidden();

				// Evaluate substance pills
				var hasSubstances = (typeof substancesList !== "undefined" && substancesList.length > 0);
				var hiddenSubstancesInput = document.getElementById("substances-hidden");
				if (!hasSubstances && hiddenSubstancesInput && hiddenSubstancesInput.value.trim().length > 0) {
					var preloaded = splitTermTokens(hiddenSubstancesInput.value)
						.filter(function(t) { return t.length >= MIN_TERM_LENGTH; })
						.slice(0, MAX_SEARCH_TERMS);
					hasSubstances = preloaded.length > 0;
				}

				// Evaluate active cluster thresholds accurately across document
				var checkedClusterBoxes = document.querySelectorAll(".cluster-filter-check[data-cluster]:checked");
				var hasThresholds = checkedClusterBoxes.length > 0;

				// Evaluate the concentration range card.
				var concCheck = document.getElementById("conc-filter-check");
				var hasConc = !!(concCheck && concCheck.checked);
				var concMinInput = document.getElementById("conc-min-input");
				var concMaxInput = document.getElementById("conc-max-input");
				if (concMinInput) concMinInput.disabled = !hasConc;
				if (concMaxInput) concMaxInput.disabled = !hasConc;
				if (!hasConc) {
					if (concMinInput) concMinInput.value = "";
					if (concMaxInput) concMaxInput.value = "";
				}

				// Synchronize checked cluster hidden inputs with current slider values
				checkedClusterBoxes.forEach(function(chk) {
					var key = chk.getAttribute("data-cluster");
					var input = document.getElementById("input-" + key);
					var ctrl = document.getElementById("ctrl-" + key);
					var slider = ctrl ? ctrl.querySelector(".threshold-slider") : null;
					if (input) {
						input.disabled = false;
						if (!input.value) {
							input.value = slider ? slider.value : "70";
						}
					}
				});

				// Disable any unchecked cluster inputs
				var uncheckedClusterBoxes = document.querySelectorAll(".cluster-filter-check[data-cluster]:not(:checked)");
				uncheckedClusterBoxes.forEach(function(chk) {
					var key = chk.getAttribute("data-cluster");
					var input = document.getElementById("input-" + key);
					if (input) {
						input.disabled = true;
						input.value = "";
					}
				});

				// A query is valid if at least one of keyword, cluster, or
				// concentration range is active (Case D is invalid).
				if (!hasSubstances && !hasThresholds && !hasConc) {
					e.preventDefault();
					showAdvancedHint("Enter a valid search term (min " + MIN_TERM_LENGTH + " characters) or select a filter");
					var tagBoxInput = document.getElementById("tag-text-input");
					if (tagBoxInput) tagBoxInput.focus();
					return false;
				}

				if (hadShortTerms) {
					showAdvancedHint("Terms shorter than " + MIN_TERM_LENGTH + " characters were ignored");
				} else {
					clearAdvancedHint();
				}

				// Strict isolation: clear top search bar input so no synthetic string is submitted or shown
				if (mainInput) {
					mainInput.removeAttribute("required");
					mainInput.value = "";
				}
			} else {
				// BASIC SEARCH MODE (Advanced panel is collapsed):
				// Strict isolation: ignore and disable all background advanced inputs for this submission
				var hiddenSubstances = document.getElementById("substances-hidden");
				if (hiddenSubstances) hiddenSubstances.disabled = true;

				var thresholdInputs = document.querySelectorAll("input[name^='threshold_']");
				thresholdInputs.forEach(function(ti) { ti.disabled = true; });

				var concInputs = document.querySelectorAll("input[name='min_conc'], input[name='max_conc']");
				concInputs.forEach(function(ci) { ci.disabled = true; });

				var skipCheck = document.getElementById("skip-svg-check");
				if (skipCheck) skipCheck.disabled = true;

				// Validate basic search input: must not be empty or pure whitespace
				var queryVal = mainInput ? mainInput.value.trim() : "";
				if (!queryVal) {
					e.preventDefault();
					if (mainInput) {
						mainInput.value = "";
						mainInput.focus();
					}
					showToast("Please enter a compound name or SMILES");
					return false;
				}

				if (mainInput) {
					mainInput.value = queryVal;
				}
			}
		});
	});
}

function flushPendingTagInput() {
	var tagInput = document.getElementById("tag-text-input");
	if (tagInput && tagInput.value.trim().length > 0) {
		addTag(tagInput.value);
		tagInput.value = "";
	}
}

function addTag(text) {
	var rawTokens = splitTermTokens(text);
	if (rawTokens.length === 0) return;

	// Ignore tokens below the minimum keyword length.
	var validTokens = rawTokens.filter(function(t) { return t.length >= MIN_TERM_LENGTH; });
	var hadShort = validTokens.length < rawTokens.length;

	if (validTokens.length === 0) {
		if (hadShort) {
			showAdvancedHint("Search terms must be at least " + MIN_TERM_LENGTH + " characters");
		}
		return;
	}

	var hitLimit = false;
	validTokens.forEach(function(tok) {
		// Prevent duplicate identical tags
		if (substancesList.includes(tok)) return;
		// Enforce the strict 5-term cap, keeping the first 5 entries.
		if (substancesList.length >= MAX_SEARCH_TERMS) {
			hitLimit = true;
			return;
		}
		substancesList.push(tok);
	});

	renderTags();
	syncSubstancesHidden();

	if (hitLimit) {
		showToast("Maximum of " + MAX_SEARCH_TERMS + " search terms allowed");
	} else if (hadShort) {
		showAdvancedHint("Terms shorter than " + MIN_TERM_LENGTH + " characters were ignored");
	} else {
		clearAdvancedHint();
	}
}

function removeTag(index) {
	if (index >= 0 && index < substancesList.length) {
		substancesList.splice(index, 1);
		renderTags();
		syncSubstancesHidden();
	}
}

function renderTags() {
	var container = document.getElementById("tags-list");
	if (!container) return;
	container.innerHTML = "";

	substancesList.forEach(function(tag, idx) {
		var pill = document.createElement("span");
		pill.className = "substance-pill";

		var label = document.createElement("span");
		label.innerText = tag;
		pill.appendChild(label);

		var removeBtn = document.createElement("button");
		removeBtn.type = "button";
		removeBtn.className = "pill-remove-btn";
		removeBtn.innerHTML = "&times;";
		removeBtn.setAttribute("aria-label", "Remove " + tag);
		removeBtn.onclick = function(e) {
			e.stopPropagation();
			removeTag(idx);
		};
		pill.appendChild(removeBtn);

		container.appendChild(pill);
	});
}

function syncSubstancesHidden() {
	var hiddenInput = document.getElementById("substances-hidden");
	if (hiddenInput) {
		hiddenInput.value = substancesList.join(",");
	}
}

function toggleClusterFilter(clusterKey, isChecked) {
	var card = document.getElementById("card-" + clusterKey);
	var ctrl = document.getElementById("ctrl-" + clusterKey);
	var hiddenInput = document.getElementById("input-" + clusterKey);
	var slider = ctrl ? ctrl.querySelector(".threshold-slider") : null;

	if (isChecked) {
		// Enforce single-cluster selection: deselect every other active cluster.
		document.querySelectorAll(".cluster-filter-check[data-cluster]").forEach(function(chk) {
			var otherKey = chk.getAttribute("data-cluster");
			if (otherKey !== clusterKey && chk.checked) {
				chk.checked = false;
				toggleClusterFilter(otherKey, false);
			}
		});
		if (card) card.classList.add("is-active");
		if (ctrl) ctrl.classList.remove("hidden");
		if (hiddenInput) {
			hiddenInput.disabled = false;
			hiddenInput.value = slider ? slider.value : "70";
		}
	} else {
		if (card) card.classList.remove("is-active");
		if (ctrl) ctrl.classList.add("hidden");
		if (hiddenInput) {
			hiddenInput.disabled = true;
			hiddenInput.value = "";
		}
	}
}

function toggleConcFilter(isChecked) {
	var card = document.getElementById("conc-filter-card");
	var ctrl = document.getElementById("conc-threshold-ctrl");
	var minInput = document.getElementById("conc-min-input");
	var maxInput = document.getElementById("conc-max-input");
	var sliderMin = document.getElementById("conc-range-min");
	var sliderMax = document.getElementById("conc-range-max");

	if (isChecked) {
		if (card) card.classList.add("is-active");
		if (ctrl) ctrl.classList.remove("hidden");
		if (minInput) {
			minInput.disabled = false;
			if (!minInput.value && sliderMin) minInput.value = sliderMin.value;
		}
		if (maxInput) {
			maxInput.disabled = false;
			if (!maxInput.value && sliderMax) maxInput.value = sliderMax.value;
		}
	} else {
		if (card) card.classList.remove("is-active");
		if (ctrl) ctrl.classList.add("hidden");
		if (minInput) {
			minInput.disabled = true;
			minInput.value = "";
		}
		if (maxInput) {
			maxInput.disabled = true;
			maxInput.value = "";
		}
	}
}

function updateThresholdVal(clusterKey, val) {
	var valBox = document.getElementById("val-" + clusterKey);
	var hiddenInput = document.getElementById("input-" + clusterKey);

	if (valBox) valBox.innerText = val + "%";
	if (hiddenInput && !hiddenInput.disabled) {
		hiddenInput.value = val;
	}
}

function resetAdvancedFilters() {
	// 1. Clear tags
	substancesList = [];
	renderTags();
	syncSubstancesHidden();
	var tagInput = document.getElementById("tag-text-input");
	if (tagInput) tagInput.value = "";

	// 2. Uncheck all cluster filters
	var checks = document.querySelectorAll(".cluster-filter-check[data-cluster]");
	checks.forEach(function(chk) {
		chk.checked = false;
		var key = chk.getAttribute("data-cluster");
		if (key) toggleClusterFilter(key, false);
	});

	// 3. Reset the concentration range filter
	var concCheck = document.getElementById("conc-filter-check");
	if (concCheck) concCheck.checked = false;
	toggleConcFilter(false);
	var concMin = document.getElementById("conc-range-min");
	var concMax = document.getElementById("conc-range-max");
	if (concMin && concMax) {
		concMin.value = concMin.getAttribute("data-default") || "0.2";
		concMax.value = concMax.getAttribute("data-default") || "50";
		concMin.dispatchEvent(new Event("input", { bubbles: true }));
	}

	// 4. Uncheck skip SVG rendering option
	var skipCheck = document.getElementById("skip-svg-check");
	if (skipCheck) skipCheck.checked = false;

	// 5. Clear any inline validation hint
	clearAdvancedHint();
}