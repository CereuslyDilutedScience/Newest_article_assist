function renderPages(pages, viewer) {
    pages.forEach((page) => {
        const pageWrapper = document.createElement("div");
        pageWrapper.className = "page-wrapper";

        // Page image
        const img = document.createElement("img");
        img.src = page.image_url;
        img.className = "page-image";

        // Overlay container
        const overlay = document.createElement("div");
        overlay.className = "text-overlay";

        img.onload = () => {
            const scaleX = img.clientWidth / page.width;
            const scaleY = img.clientHeight / page.height;

            overlay.style.width = img.clientWidth + "px";
            overlay.style.height = img.clientHeight + "px";

            page.words.forEach((word) => {
                if (word.skip) return;

                const span = document.createElement("span");
                span.className = "word";

                // Always show the REAL PDF text
                span.textContent = word.text;
                span.style.color = "transparent";

                // Add definition tooltip if present
                if (word.definition) {
                    span.classList.add("has-definition");
                    span.title = word.definition;
                }

                // Positioning
                span.style.left = (word.x * scaleX) + "px";
                span.style.top  = (word.y * scaleY) + "px";

                // Corrected text box sizing
                const scaledFont = word.height * scaleY;
                span.style.fontSize = scaledFont + "px";
                span.style.lineHeight = scaledFont + "px";   // <-- FIXED

                overlay.appendChild(span);
            });
        };

        pageWrapper.appendChild(img);
        pageWrapper.appendChild(overlay);
        viewer.appendChild(pageWrapper);
    });
}
