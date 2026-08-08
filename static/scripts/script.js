var menu_opened = false;

function trigger_menu(){
	var icon = document.getElementById("icon");
	var menu = document.getElementById("menu");

	if (menu_opened == false){
		menu_opened = true;
		menu.style.visibility = "visible";
		menu.style.opacity = "1";
		icon.style.transform = "rotate(90deg)"
	}
	else{
		menu_opened = false;
		menu.style.opacity = "0";
		menu.style.visibility = "hidden";
		icon.style.transform = "rotate(0deg)"
	}
}

/*async function copy(text, el){
	navigator.clipboard.writeText("augh")

	el.querySelector(".text-in-cell").innerHTML = "successfully copied to clipboard";

	await new Promise(resolve => setTimeout(resolve, 2000));

	el.querySelector(".text-in-cell").innerHTML = text;
}*/

function copy(textToCopy, element) {
    // navigator clipboard api needs a secure context (https)
    if (navigator.clipboard && window.isSecureContext) {
        // navigator clipboard api method'
        setTimeout(function() {
          element.innerHTML = textToCopy;
        }, 1750);
        element.innerHTML = "copied to clipboard";
        return navigator.clipboard.writeText(textToCopy);
	    element.innerHTML = "fertig";
    } else {
        // text area method
        let textArea = document.createElement("textarea");
        textArea.value = textToCopy;
        // make the textarea out of viewport
        textArea.style.position = "fixed";
        textArea.style.left = "-999999px";
        textArea.style.top = "-999999px";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        setTimeout(function() {
          element.innerHTML = textToCopy;
        }, 1750);
        element.innerHTML = "copied to clipboard";
        return new Promise((res, rej) => {
            // here the magic happens
            document.execCommand('copy') ? res() : rej();
            textArea.remove();
        });
    }
}