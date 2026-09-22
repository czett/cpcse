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
	if (!textToCopy) return;

	if (navigator.clipboard && window.isSecureContext) {
		navigator.clipboard.writeText(textToCopy).then(function() {
			handleCopyFeedback(element);
		}).catch(function() {
			fallbackCopyText(textToCopy, element);
		});
	} else {
		fallbackCopyText(textToCopy, element);
	}
}

function copyText(textToCopy, element) {
	copySmile(textToCopy, element);
}

function fallbackCopyText(textToCopy, element) {
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
		handleCopyFeedback(element);
	} catch (err) {
		console.error('Fallback copy failed', err);
	}
	textArea.remove();
}

function handleCopyFeedback(element) {
	showToast("SMILES string copied!");
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

// Input clear button listener
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
});