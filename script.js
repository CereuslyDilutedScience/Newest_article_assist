document.getElementById("uploadForm").addEventListener("submit", async (e) => {
    e.preventDefault();

    const fileInput = document.getElementById("pdfFile");
    if (!fileInput.files.length) {
        alert("Please upload a PDF first.");
        return;
    }

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    const response = await fetch("https://YOUR-RENDER-URL/extract", {
        method: "POST",
        body: formData
    });

    const data = await response.json();
    renderPages(data.pages);
});


function renderPages(pages) {
    const container = document.getElementById("output");
    container.innerHTML = "";

    pages.forEach((page) => {
        const pageWrapper = document.createElement("div");
        pageWrapper.className = "page-wrapper";

        // Create image element
        const img = document.createElement("img");
        img.src = page.image_url;
        img.className = "page-image";

        // Overlay container
        const overlay = document.createElement("div");
        overlay.className = "text-overlay";

        img.onload = () => {
            const scaleX = img.clientWidth / page.width;
            const scaleY = img.clientHeight / page.height;

            page.words.forEach((word) => {
                if (word.skip) return; // skip words inside multi-word phrases

                const span = document.createElement("span");
                span.className = "word";
                span.textContent = word.term || word.text;

                // Tooltip for definitions
                if (word.definition) {
                    span.classList.add("has-definition");
                    span.title = word.definition;
                }

                // Positioning
                span.style.left = (word.x * scaleX) + "px";
                span.style.top = (word.y * scaleY) + "px";
                span.style.fontSize = (word.height * scaleY) + "px";

                overlay.appendChild(span);
            });
        };

        pageWrapper.appendChild(img);
        pageWrapper.appendChild(overlay);
        container.appendChild(pageWrapper);
    });
}
