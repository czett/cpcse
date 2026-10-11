var menu_opened = false;

function trigger_menu() {
	var icon = document.getElementById("icon");
	var menu = document.getElementById("menu");
	if (!menu) return;

	if (menu_opened === false) {
		menu_opened = true;
		menu.classList.add("mobile-menu-active");
		if (icon) icon.style.transform = "rotate(90deg)";
	} else {
		menu_opened = false;
		menu.classList.remove("mobile-menu-active");
		if (icon) icon.style.transform = "rotate(0deg)";
	}
}

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

	initTagInput();
});

// ==========================================================================
// ADVANCED SEARCH INTERACTIVITY
// ==========================================================================

var substancesList = [];

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
		// Focus tag input if visible
		var tagInput = document.getElementById("tag-text-input");
		if (tagInput) tagInput.focus();
	} else {
		panel.classList.add("hidden");
		if (toggleBtn) {
			toggleBtn.classList.remove("active");
			toggleBtn.setAttribute("aria-expanded", "false");
		}
	}
}

function focusTagInput() {
	var tagInput = document.getElementById("tag-text-input");
	if (tagInput) tagInput.focus();
}

function initTagInput() {
	var tagInput = document.getElementById("tag-text-input");
	if (!tagInput) return;

	tagInput.addEventListener("keydown", function(e) {
		if (e.key === "," || e.key === "Enter" || e.key === "Tab") {
			var val = this.value.trim().replace(/^,+|,+$/g, "");
			if (val.length > 0) {
				e.preventDefault();
				addTag(val);
				this.value = "";
			}
		} else if (e.key === "Backspace" && this.value === "" && substancesList.length > 0) {
			removeTag(substancesList.length - 1);
		}
	});

	tagInput.addEventListener("blur", function() {
		var val = this.value.trim().replace(/^,+|,+$/g, "");
		if (val.length > 0) {
			addTag(val);
			this.value = "";
		}
	});
}

function addTag(text) {
	var clean = text.trim();
	if (!clean) return;
	// Prevent duplicate identical tags
	if (substancesList.includes(clean)) return;

	substancesList.push(clean);
	renderTags();
	syncSubstancesHidden();
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
		if (card) card.classList.add("is-active");
		if (ctrl) ctrl.classList.remove("hidden");
		if (hiddenInput) {
			hiddenInput.disabled = false;
			hiddenInput.value = slider ? slider.value : "80";
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
	var checks = document.querySelectorAll(".cluster-filter-check");
	checks.forEach(function(chk) {
		chk.checked = false;
		var key = chk.getAttribute("data-cluster");
		if (key) toggleClusterFilter(key, false);
	});

	// 3. Uncheck skip SVG rendering option
	var skipCheck = document.getElementById("skip-svg-check");
	if (skipCheck) skipCheck.checked = false;
}