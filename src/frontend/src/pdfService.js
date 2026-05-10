/**
 * pdfService – Loads pdf.js and decodes Data URLs into Uint8Array.
 * Avoids duplication between App.jsx (embed + feedAI) and importModal.jsx.
 */

const PDFJS_CDN = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
const PDFJS_WORKER_CDN = "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";

let loadPromise = null;

export async function loadPdfJs() {
  if (window.pdfjsLib) return window.pdfjsLib;
  if (loadPromise) return loadPromise;

  loadPromise = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = PDFJS_CDN;
    s.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_CDN;
      resolve(window.pdfjsLib);
    };
    s.onerror = reject;
    document.head.appendChild(s);
  });

  return loadPromise;
}

export function dataUrlToBytes(dataUrl) {
  const base64 = dataUrl.split(",")[1];
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export async function getPdfDocument(dataUrl) {
  const pdfjsLib = await loadPdfJs();
  const bytes = dataUrlToBytes(dataUrl);
  return pdfjsLib.getDocument({ data: bytes }).promise;
}
